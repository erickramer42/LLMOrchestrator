"""The server over Streamable HTTP (ADR-0004): tokens and scopes, the audit
log, the limits, Host and Origin checks, and the startup refusals. A real
uvicorn server on a free loopback port, with the model faked at the HTTP
layer as in test_server. No Ollama, no network beyond loopback.

Run from the repo root:
    python -m unittest discover -s tests_mcp -v
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import anyio
import httpx2
import uvicorn

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import agent_client  # noqa: E402
import debate  # noqa: E402
from mcp_server import __version__  # noqa: E402
from mcp_server.guard import RateLimiter, redact  # noqa: E402
from mcp_server.http_server import HttpOptions, build_app, check_options  # noqa: E402
from mcp_server.jobs import ReviewQueue  # noqa: E402
from mcp_server.server import Settings  # noqa: E402
from mcp_server.tokens import TokenStore, effective_scopes, token_hash  # noqa: E402
from test_server import DIFF, ENGINEER_CLEAN, REVIEWER_CLEAN, fake_ollama  # noqa: E402

# Distinctive text that must never reach the audit log
DIFF_MARK = "SECRET_DIFF_MARKER_7f3a"
PROPOSAL_MARK = "SECRET_PROPOSAL_MARKER_91c2"
MARKED_DIFF = DIFF + f"+// {DIFF_MARK}\n"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HttpTestCase(unittest.TestCase):
    """A server per test on temporary directories, with a review token and
    a read token."""

    def setUp(self):
        sleeper = mock.patch.object(agent_client.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.records = self.tmp / "records"
        self.store = TokenStore(self.tmp / "tokens.json")
        self.review_token = self.store.add("reviewer", ["review"])
        self.read_token = self.store.add("reader", ["read"])

    def start(self, queue=None, limiter=None, **settings):
        s = Settings(records_dir=self.records, index_dir=self.tmp / "indexes",
                     tokens_file=self.store.path, **settings)
        port = free_port()
        app, self.mcp = build_app(HttpOptions(port=port), s, queue, limiter)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                               log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(server.started)

        def stop():
            server.should_exit = True
            thread.join(10)
        self.addCleanup(stop)
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.audit_path = s.audit_path

    def calls(self, token, *calls):
        """Run (tool, args) calls in one connection; their results."""
        async def go():
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            async with httpx2.AsyncClient(headers=headers, timeout=30) as hc:
                async with Client(streamable_http_client(self.url, http_client=hc)) as c:
                    return [await c.call_tool(tool, args) for tool, args in calls]
        return anyio.run(go)

    def review(self, token, args):
        res, = self.calls(token, ("review_diff", args))
        self.assertFalse(res.is_error, res.content)
        state = res.structured_content
        for _ in range(30):
            if state["status"] in ("done", "failed", "lost"):
                break
            res, = self.calls(token, ("get_decision",
                                      {"record_id": state["record_id"], "wait_seconds": 1}))
            state = res.structured_content
        return state

    def raw_post(self, headers):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        with httpx2.Client(timeout=10) as hc:
            return hc.post(self.url, json=body, headers={
                "Accept": "application/json, text/event-stream", **headers})

    def audit(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(l) for l in self.audit_path.read_text(encoding="utf-8").splitlines()]


class AuthTests(HttpTestCase):

    def test_no_token_a_wrong_token_and_a_revoked_token_get_401_and_audit_lines(self):
        self.start()
        revoked = self.store.add("gone", ["review"])
        self.assertTrue(self.store.revoke("gone"))
        with fake_ollama() as post:
            statuses = [self.raw_post(h).status_code for h in (
                {}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Bearer {revoked}"})]
        self.assertEqual(statuses, [401, 401, 401])
        self.assertEqual(post.call_count, 0)
        refused = [e for e in self.audit() if e.get("event") == "http_refused"]
        self.assertEqual([e["status"] for e in refused], [401, 401, 401])
        self.assertTrue(all(e["caller"] is None for e in refused))
        self.assertFalse(self.records.exists() and any(self.records.glob("decision_*")))

    def test_revoking_a_token_takes_effect_without_a_restart(self):
        self.start()
        self.assertFalse(self.calls(self.read_token, ("list_decisions", {}))[0].is_error)
        self.store.revoke("reader")
        self.assertEqual(self.raw_post({"Authorization": f"Bearer {self.read_token}"}).status_code,
                         401)

    def test_a_read_token_reads_but_cannot_review(self):
        self.start()
        with fake_ollama() as post:
            listed, review, resource = self.calls(
                self.read_token, ("list_decisions", {}),
                ("review_diff", {"proposal": "p", "diff": DIFF}),
                ("get_decision", {"record_id": "debate_20200101_000000_abcdef"}))
        self.assertFalse(listed.is_error)
        self.assertTrue(review.is_error)
        self.assertIn("insufficient_scope", review.content[0].text)
        self.assertEqual(post.call_count, 0)
        lines = [e for e in self.audit() if e.get("tool") == "review_diff"]
        self.assertEqual([(e["caller"], e["outcome"]) for e in lines],
                         [("reader", "insufficient_scope")])

    def test_a_review_token_runs_a_review_and_every_step_is_audited(self):
        self.start()
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            final = self.review(self.review_token, {"proposal": "p", "diff": DIFF})
        self.assertEqual(final["final_verdict"], "APPROVED_FOR_MERGE")
        self.assertEqual(final["server_version"], __version__)
        rec = json.loads((self.records / f"decision_{final['record_id']}.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(rec["metadata"]["interface"],
                         {"name": "mcp", "server_version": __version__,
                          "transport": "http", "caller": "reviewer"})
        lines = self.audit()
        submit = next(e for e in lines if e.get("tool") == "review_diff")
        self.assertEqual((submit["caller"], submit["outcome"], submit["transport"]),
                         ("reviewer", "ok", "http"))
        self.assertEqual(submit["record_id"], final["record_id"])
        done = [e for e in lines if e.get("tool") == "get_decision" and e.get("status") == "done"]
        if done:  # the review may finish before the first get_decision
            self.assertEqual(done[-1]["final_verdict"], "APPROVED_FOR_MERGE")
            self.assertEqual(done[-1]["model_tokens"]["attempts"], 2)
        self.assertTrue(all(e["server_version"] == __version__ for e in lines))


class VerifyScopeTests(HttpTestCase):

    def test_verify_findings_needs_the_review_scope_and_no_review_slot(self):
        # It runs no model, so the hourly review limit does not apply.
        self.start(reviews_per_hour=0)
        args = {"diff": DIFF, "findings": [{"claim": "x is wrong", "quote": "msg->len"}]}
        with fake_ollama() as post:
            read, = self.calls(self.read_token, ("verify_findings", args))
            checked, review = self.calls(self.review_token, ("verify_findings", args),
                                         ("review_diff", {"proposal": "p", "diff": DIFF}))
        self.assertEqual(post.call_count, 0)
        self.assertTrue(read.is_error)
        self.assertIn("insufficient_scope", read.content[0].text)
        self.assertFalse(checked.is_error, checked.content)
        self.assertTrue(review.is_error)
        self.assertIn("rate_limited", review.content[0].text)

    def test_the_task_worker_tools_need_the_review_scope_and_items_are_hashed(self):
        self.start()
        args = {"task_id": "task_20260101_000000_abcdef",
                "items": [{"finding": 0, "verdict": "unclear"}]}
        claim, answer = self.calls(self.read_token, ("claim_task", {"task_id": args["task_id"]}),
                                   ("submit_result", args))
        listed, = self.calls(self.read_token, ("list_tasks", {}))
        for res in (claim, answer):
            self.assertTrue(res.is_error)
            self.assertIn("insufficient_scope", res.content[0].text)
        self.assertFalse(listed.is_error, listed.content)
        logged = [e for e in self.audit() if e.get("tool") == "submit_result"][0]
        self.assertEqual(set(logged["arguments"]["items"]), {"sha256", "items"})

    def test_redact_hashes_a_findings_list(self):
        out = redact({"findings": [{"claim": "c", "quote": "q"}]})
        self.assertEqual(set(out["findings"]), {"sha256", "items"})
        self.assertEqual(out["findings"]["items"], 1)


class AuditContentTests(HttpTestCase):

    def test_no_token_or_reviewed_text_reaches_the_audit_log(self):
        self.start()
        args = {"proposal": f"Change {PROPOSAL_MARK}", "diff": MARKED_DIFF,
                "context": f"// {DIFF_MARK} context"}
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            self.review(self.review_token, args)
        self.raw_post({"Authorization": f"Bearer {self.review_token}x"})
        text = self.audit_path.read_text(encoding="utf-8")
        for secret in (DIFF_MARK, PROPOSAL_MARK, self.review_token, self.read_token):
            self.assertNotIn(secret, text)
        self.assertIn(debate.text_sha256(MARKED_DIFF), text)
        submit = next(e for e in self.audit() if e.get("tool") == "review_diff")
        self.assertEqual(submit["arguments"]["diff"],
                         {"sha256": debate.text_sha256(MARKED_DIFF), "chars": len(MARKED_DIFF)})

    def test_redact_keeps_other_arguments(self):
        out = redact({"diff": "x", "proposal": 3, "record_id": "debate_x", "limit": 5})
        self.assertEqual(out["diff"]["chars"], 1)
        self.assertEqual(out["proposal"], {"type": "int"})
        self.assertEqual((out["record_id"], out["limit"]), ("debate_x", 5))


class LimitTests(HttpTestCase):

    def test_calls_over_the_minute_limit_are_refused_per_caller(self):
        self.start(calls_per_min=3)
        results = self.calls(self.read_token, *[("list_decisions", {})] * 4)
        self.assertEqual([r.is_error for r in results], [False, False, False, True])
        self.assertIn("rate_limited", results[3].content[0].text)
        # Another caller has its own window
        self.assertFalse(self.calls(self.review_token, ("list_decisions", {}))[0].is_error)
        outcomes = [e["outcome"] for e in self.audit() if e.get("caller") == "reader"]
        self.assertEqual(outcomes, ["ok", "ok", "ok", "rate_limited"])

    def test_reviews_over_the_hourly_limit_are_refused(self):
        self.start(reviews_per_hour=1)
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            self.review(self.review_token, {"proposal": "p", "diff": DIFF})
            second, = self.calls(self.review_token, ("review_diff", {"proposal": "p", "diff": DIFF}))
        self.assertTrue(second.is_error)
        self.assertIn("reviews an hour", second.content[0].text)

    def test_a_caller_cannot_hold_more_than_its_share_of_the_queue(self):
        release = threading.Event()

        def slow(*_a, **_k):
            release.wait(10)
            raise OSError("stopped")
        queue = ReviewQueue(self.records, {"name": "mcp"}, max_pending=4, run=slow)
        self.start(queue, max_reviews_per_caller=1)
        try:
            first, second = self.calls(self.review_token,
                                       ("review_diff", {"proposal": "p", "diff": DIFF}),
                                       ("review_diff", {"proposal": "p", "diff": DIFF}))
            self.assertFalse(first.is_error)
            self.assertTrue(second.is_error)
            self.assertIn("queued or running", second.content[0].text)
        finally:
            release.set()
            queue.join()

    def test_the_limiter_window_slides(self):
        now = [0.0]
        limiter = RateLimiter(2, 1, clock=lambda: now[0])
        self.assertIsNone(limiter.take_call("a"))
        self.assertIsNone(limiter.take_call("a"))
        self.assertAlmostEqual(limiter.take_call("a"), 60.0)
        now[0] = 60.5
        self.assertIsNone(limiter.take_call("a"))
        self.assertIsNone(limiter.take_review("a"))
        self.assertIsNotNone(limiter.take_review("a"))

    def test_a_limit_of_zero_refuses_instead_of_failing(self):
        limiter = RateLimiter(0, 0, clock=lambda: 0.0)
        self.assertEqual((limiter.take_call("a"), limiter.take_review("a")), (60.0, 3600.0))


class HostAndOriginTests(HttpTestCase):

    def test_a_foreign_origin_gets_403_and_a_foreign_host_421(self):
        self.start()
        auth = {"Authorization": f"Bearer {self.read_token}"}
        self.assertEqual(self.raw_post({**auth, "Origin": "http://evil.example"}).status_code, 403)
        self.assertEqual(self.raw_post({**auth, "Host": "evil.example"}).status_code, 421)
        self.assertNotEqual(self.raw_post(auth).status_code, 403)
        refused = [e["status"] for e in self.audit() if e.get("event") == "http_refused"]
        self.assertEqual(refused, [403, 421])


class StartupTests(HttpTestCase):

    def settings(self, tokens=True):
        return Settings(records_dir=self.records, index_dir=self.tmp,
                        tokens_file=self.store.path if tokens else self.tmp / "none.json")

    def test_a_non_loopback_host_needs_tls_or_an_explicit_opt_out(self):
        with self.assertRaisesRegex(ValueError, "not a loopback"):
            check_options(HttpOptions(host="0.0.0.0"), self.settings())
        with self.assertRaisesRegex(ValueError, "go together"):
            check_options(HttpOptions(host="0.0.0.0", certfile="c.pem"), self.settings())
        check_options(HttpOptions(host="0.0.0.0", insecure_http=True), self.settings())
        check_options(HttpOptions(host="0.0.0.0", certfile="c.pem", keyfile="k.pem"),
                      self.settings())
        for host in ("127.0.0.1", "localhost", "::1"):
            check_options(HttpOptions(host=host), self.settings())

    def test_the_http_server_refuses_to_start_without_tokens(self):
        with self.assertRaisesRegex(ValueError, "no tokens"):
            check_options(HttpOptions(), self.settings(tokens=False))


class TokenStoreTests(HttpTestCase):

    def test_the_file_holds_hashes_never_tokens(self):
        text = self.store.path.read_text(encoding="utf-8")
        self.assertNotIn(self.review_token, text)
        self.assertIn(token_hash(self.review_token), text)
        self.assertEqual(self.store.verify(self.review_token)["id"], "reviewer")
        self.assertIsNone(self.store.verify(self.review_token + "x"))
        self.assertIsNone(self.store.verify(""))

    def test_ids_and_scopes_are_checked(self):
        for token_id, scopes in (("../x", ["read"]), ("", ["read"]), ("ok", ["admin"]),
                                 ("ok", []), ("reviewer", ["read"])):
            with self.assertRaises(ValueError, msg=(token_id, scopes)):
                self.store.add(token_id, scopes)
        self.assertEqual(effective_scopes(["review"]), ["read", "review"])
        self.assertEqual(effective_scopes(["read"]), ["read"])

    def test_the_token_command_adds_lists_and_revokes(self):
        env = {**os.environ, "LLMORCH_TOKENS_FILE": str(self.tmp / "cli.json")}
        run = lambda *a: subprocess.run([sys.executable, str(REPO_ROOT / "mcp_server"), "token", *a],
                                        cwd=self.tmp, env=env, capture_output=True, text=True,
                                        timeout=60)
        added = run("add", "ci", "--scope", "read")
        self.assertEqual(added.returncode, 0, added.stderr)
        token = added.stdout.strip().splitlines()[-1]
        self.assertEqual(TokenStore(self.tmp / "cli.json").verify(token)["id"], "ci")
        self.assertIn("ci\tread", run("list").stdout)
        self.assertEqual(run("revoke", "ci").returncode, 0)
        self.assertEqual(run("revoke", "ci").returncode, 1)
        self.assertNotEqual(run("add", "x", "--scope", "admin").returncode, 0)


if __name__ == "__main__":
    unittest.main()
