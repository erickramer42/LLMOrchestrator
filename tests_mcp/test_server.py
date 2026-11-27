"""MCP server tests (ADR-0003): an in-process MCP client calls every tool
and resource against the fake model server; one test launches the server
over stdio from another directory. No Ollama, no network.

Needs requirements-mcp.txt. Run from the repo root:
    python -m unittest discover -s tests_mcp -v
"""

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import anyio
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mcp import Client, StdioServerParameters  # noqa: E402

import adjudication  # noqa: E402
import agent_client  # noqa: E402
import debate  # noqa: E402
from mcp_server import __version__  # noqa: E402
from mcp_server.jobs import ReviewQueue, marker_path  # noqa: E402
from mcp_server.server import MAX_FIELD_CHARS, Settings, build_server  # noqa: E402
from tasks.board import Board  # noqa: E402
from test_tasks import FINDING as TASK_FINDING  # noqa: E402
from test_tasks import item as task_item, make_project  # noqa: E402

logging.getLogger("agent_client").addHandler(logging.NullHandler())

REVIEWER_CLEAN = {"verdict": "approve", "blockers": [], "questions": [], "nits": []}
ENGINEER_CLEAN = {"verdict": "approve", "blockers": [], "concerns": [], "questions": []}
QUOTE = "memcpy(buf, msg->data, msg->len);"
DIFF = f"+++ b/core/src/x.cpp\n@@ -0,0 +1 @@\n+{QUOTE}\n"
TASK_ITEM = task_item()


class FakeResp:
    """Minimal stand-in for an Ollama /api/chat response."""

    def __init__(self, content):
        self._body = {"message": {"content": json.dumps(content)}, "done_reason": "stop"}
        self.text = json.dumps(self._body)

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def fake_ollama(*replies):
    seq = [r if isinstance(r, Exception) else FakeResp(r) for r in replies]
    return mock.patch.object(agent_client.requests, "post", side_effect=seq)


def run(coro_fn, *args):
    return anyio.run(coro_fn, *args)


class ServerTestCase(unittest.TestCase):
    """A server on temporary directories, the working directory elsewhere,
    and stdout captured: over stdio, stdout is the protocol."""

    def setUp(self):
        sleeper = mock.patch.object(agent_client.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.records = self.tmp / "records"
        self.indexes = self.tmp / "indexes"
        self.indexes.mkdir()
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        self.stdout = io.StringIO()
        redirect = contextlib.redirect_stdout(self.stdout)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        stderr = contextlib.redirect_stderr(io.StringIO())
        stderr.__enter__()
        self.addCleanup(stderr.__exit__, None, None, None)

    def server(self, queue=None, **settings):
        s = Settings(records_dir=self.records, index_dir=self.indexes, **settings)
        return build_server(s, queue)

    def call(self, server, tool, args, **kw):
        async def go():
            async with Client(server) as c:
                return await c.call_tool(tool, args, **kw)
        return run(go)

    def review(self, server, args, wait=30):
        """Submit, then follow the review to its end; the final state."""
        async def go():
            async with Client(server) as c:
                sub = await c.call_tool("review_diff", args)
                self.assertFalse(sub.is_error, sub.content)
                rid = sub.structured_content["record_id"]
                state = sub.structured_content
                for _ in range(wait):
                    if state["status"] in ("done", "failed", "lost"):
                        break
                    res = await c.call_tool("get_decision",
                                            {"record_id": rid, "wait_seconds": 1})
                    self.assertFalse(res.is_error, res.content)
                    state = res.structured_content
                return sub.structured_content, state
        return run(go)

    def tearDown(self):
        self.assertEqual(self.stdout.getvalue(), "", "the server wrote to stdout")


class ToolTests(ServerTestCase):

    def test_tools_and_resources_are_listed(self):
        async def go():
            async with Client(self.server()) as c:
                tools = {t.name for t in (await c.list_tools()).tools}
                resources = {str(r.uri) for r in (await c.list_resources()).resources}
                templates = {t.uri_template
                             for t in (await c.list_resource_templates()).resource_templates}
                return tools, resources, templates, c.server_info
        tools, resources, templates, info = run(go)
        self.assertEqual(tools, {"review_diff", "get_decision", "list_decisions",
                                 "verify_findings", "list_tasks", "claim_task",
                                 "submit_result"})
        self.assertEqual(resources, {"index://info", "index://files", "index://types",
                                     "index://constants", "index://callsites"})
        self.assertEqual(templates, {"decision://{record_id}"})
        self.assertEqual(info.version, __version__)

    def test_tools_carry_annotations_and_the_polling_rule(self):
        # Clients that read no server instructions (Lumo Desktop) see only
        # the tools' descriptions and annotations.
        async def go():
            async with Client(self.server()) as c:
                return {t.name: t for t in (await c.list_tools()).tools}
        tools = run(go)
        for name in ("get_decision", "list_decisions", "verify_findings"):
            a = tools[name].annotations
            self.assertEqual((a.read_only_hint, a.destructive_hint, a.open_world_hint),
                             (True, False, False), name)
        a = tools["review_diff"].annotations
        self.assertEqual((a.read_only_hint, a.destructive_hint, a.idempotent_hint,
                          a.open_world_hint), (False, False, False, False))
        self.assertIn("get_decision(record_id, wait_seconds=55)", tools["review_diff"].description)
        self.assertIn("MANUAL_REVIEW_REQUIRED needs a", tools["get_decision"].description)

    def test_a_clean_review_is_queued_then_approved_with_its_record(self):
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            submitted, final = self.review(self.server(), {"proposal": "p", "diff": DIFF})
        self.assertIn(submitted["status"], ("queued", "running", "done"))
        self.assertIsNone(submitted["final_verdict"])
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["final_verdict"], "APPROVED_FOR_MERGE")
        rid = final["record_id"]
        rec = json.loads((self.records / f"decision_{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["metadata"]["interface"],
                         {"name": "mcp", "server_version": __version__,
                          "transport": "stdio", "caller": "stdio"})
        self.assertEqual(rec["inputs"]["diff_sha256"], final["diff_sha256"])
        self.assertFalse(marker_path(self.records, rid).exists())
        self.assertFalse((self.tmp / "coach_artifacts").exists())

    def test_stdio_calls_are_audited_with_the_stdio_caller(self):
        # ADR-0004: the guard runs on both transports
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            _, final = self.review(self.server(), {"proposal": "p", "diff": DIFF})
        lines = [json.loads(l) for l in
                 (self.records / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual({(e["transport"], e["caller"]) for e in lines}, {("stdio", "stdio")})
        submit = next(e for e in lines if e["tool"] == "review_diff")
        self.assertEqual((submit["outcome"], submit["record_id"]), ("ok", final["record_id"]))
        self.assertEqual(final["model_tokens"]["attempts"], 2)

    def test_findings_are_the_final_round_after_the_guardrails(self):
        # One verified blocker, one hedged (demoted to a question by judge j6).
        rev = {**REVIEWER_CLEAN, "blockers": [
            {"claim": "memcpy overflows buf", "file": "core/src/x.cpp", "quote": QUOTE},
            {"claim": "this might leak", "file": "core/src/x.cpp", "quote": QUOTE}]}
        replies = [rev, ENGINEER_CLEAN] * debate.MAX_DEBATE_ROUNDS
        with fake_ollama(*replies):
            _, final = self.review(self.server(), {"proposal": "p", "diff": DIFF})
        self.assertEqual(final["final_verdict"], adjudication.MAX_ROUNDS_VERDICT)
        self.assertEqual(final["rounds_completed"], debate.MAX_DEBATE_ROUNDS)
        found = final["findings"]["reviewer"]
        self.assertEqual(len(found["blockers"]), 1)
        self.assertIn("memcpy overflows buf", found["blockers"][0])
        self.assertTrue(any("might leak" in q for q in found["questions"]))

    def test_schema_invalid_replies_never_approve(self):
        bad = {"verdict": "approve", "summary": "looks fine"}
        with fake_ollama(bad, bad, bad):
            _, final = self.review(self.server(), {"proposal": "p", "diff": DIFF})
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["final_verdict"], adjudication.AGENT_FAILURE_VERDICT)
        self.assertTrue(any(n.startswith("agent_failure:") for n in final["notes"]))

    def test_an_unreachable_model_never_approves(self):
        err = requests.exceptions.ConnectionError("refused")
        with fake_ollama(err, err, err):
            _, final = self.review(self.server(), {"proposal": "p", "diff": DIFF})
        self.assertEqual(final["final_verdict"], adjudication.AGENT_FAILURE_VERDICT)

    def test_refused_input_is_recorded_at_once_without_a_model_call(self):
        server = self.server()
        with fake_ollama() as post:
            empty = self.call(server, "review_diff", {"proposal": "p"})
            large = self.call(server, "review_diff",
                              {"proposal": "p", "diff": "+" + "x" * 60000 + "\n"})
        self.assertEqual(post.call_count, 0)
        for res, verdict in ((empty, adjudication.NO_INPUT_VERDICT),
                             (large, adjudication.INPUT_TOO_LARGE_VERDICT)):
            self.assertFalse(res.is_error)
            self.assertEqual(res.structured_content["status"], "done")
            self.assertEqual(res.structured_content["final_verdict"], verdict)
            self.assertTrue(any(n.startswith("input_refused:")
                                for n in res.structured_content["notes"]))
        self.assertEqual(len(list(self.records.glob("decision_*.json"))), 2)

    def test_a_field_over_the_cap_is_a_tool_error(self):
        res = self.call(self.server(), "review_diff",
                        {"proposal": "p", "diff": "+" + "x" * MAX_FIELD_CHARS})
        self.assertTrue(res.is_error)
        self.assertIn("limit", res.content[0].text)

    def test_index_name_cannot_leave_the_index_directory(self):
        # The files exist, so only the name check can refuse them.
        index = (REPO_ROOT / "repo_context.json").read_text(encoding="utf-8")
        (self.tmp / "outside.json").write_text(index, encoding="utf-8")
        (self.indexes / ".hidden.json").write_text(index, encoding="utf-8")
        (self.indexes / "x.txt").write_text(index, encoding="utf-8")
        server = self.server()
        for name in ("../outside.json", "..\\outside.json", str(self.tmp / "outside.json"),
                     ".hidden.json", "x.txt", "missing.json"):
            res = self.call(server, "review_diff",
                            {"proposal": "p", "diff": DIFF, "index_name": name})
            self.assertTrue(res.is_error, name)

    def test_a_named_index_is_used(self):
        index = json.loads((REPO_ROOT / "repo_context.json").read_text(encoding="utf-8"))
        (self.indexes / "base.json").write_text(json.dumps(index), encoding="utf-8")
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            _, final = self.review(self.server(),
                                   {"proposal": "p", "diff": DIFF, "index_name": "base.json"})
        rec = json.loads((self.records / f"decision_{final['record_id']}.json")
                         .read_text(encoding="utf-8"))
        self.assertTrue(rec["metadata"]["repo_context_pack"]["index_file"].endswith("base.json"))


class VerifyTests(ServerTestCase):
    """verify_findings: other reviewers' findings under the guardrails (ADR-0005)."""

    FINDINGS = [
        {"id": "a", "claim": "memcpy copies msg->len bytes into buf unchecked",
         "file": "core/src/x.cpp", "quote": QUOTE},
        {"id": "b", "claim": "buf overflows", "file": "core/src/x.cpp",
         "quote": "memcpy(buf, msg->data, sizeof buf);"},
        {"claim": "m_lastReported races between threads", "file": "x.cpp", "quote": QUOTE},
        {"claim": "buf may overflow", "file": "core/src/x.cpp", "quote": QUOTE,
         "severity": "high"},
    ]

    def verify(self, args, server=None):
        with fake_ollama() as post:
            res = self.call(server or self.server(), "verify_findings", args)
        self.assertEqual(post.call_count, 0)
        return res

    def test_each_finding_gets_its_outcome_and_no_verdict(self):
        res = self.verify({"diff": DIFF, "findings": self.FINDINGS})
        self.assertFalse(res.is_error, res.content)
        out = res.structured_content
        self.assertEqual([(r["index"], r.get("id"), r["outcome"], r["found_in"])
                          for r in out["results"]],
                         [(0, "a", "kept", "core/src/x.cpp"), (1, "b", "quote", None),
                          (2, None, "link", "core/src/x.cpp"),
                          (3, None, "hedge", "core/src/x.cpp")])
        self.assertEqual(out["counts"], {"kept": 1, "quote": 1, "link": 1, "hedge": 1,
                                         "invalid": 0})
        self.assertTrue(all(r["meaning"] for r in out["results"]))
        self.assertNotIn("final_verdict", out)
        self.assertIn("no merge verdict", out["notes"][0])
        self.assertEqual((out["judge_version"], out["index"]),
                         (adjudication.JUDGE_VERSION, "committed"))
        self.assertFalse(self.records.exists() and any(self.records.glob("decision_*")))

    def test_a_quote_from_the_context_is_found_there(self):
        res = self.verify({"diff": "", "context": "uint8_t buf[8];",
                           "findings": [{"claim": "buf is too small", "quote": "uint8_t buf[8];"}]})
        self.assertEqual([(r["outcome"], r["found_in"]) for r in res.structured_content["results"]],
                         [("kept", "context")])

    def test_no_findings_counts_nothing_and_approves_nothing(self):
        out = self.verify({"diff": DIFF, "findings": []}).structured_content
        self.assertEqual((out["results"], sum(out["counts"].values())), ([], 0))
        self.assertNotIn("final_verdict", out)

    def test_no_code_too_many_findings_and_an_empty_claim_are_refused(self):
        for args in ({"diff": "", "findings": self.FINDINGS[:1]},
                     {"diff": DIFF, "findings": self.FINDINGS[:1] * 101},
                     {"diff": DIFF, "findings": [{"claim": "", "quote": QUOTE}]},
                     {"diff": DIFF, "findings": ["buf overflows"]},
                     {"diff": DIFF, "findings": self.FINDINGS, "index_name": "../x.json"}):
            res = self.verify(args)
            self.assertTrue(res.is_error, args)

    def test_findings_are_hashed_in_the_audit_log(self):
        self.verify({"diff": DIFF, "findings": self.FINDINGS})
        [line] = [json.loads(l) for l in
                  (self.records / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((line["tool"], line["outcome"], line["counts"]["kept"]),
                         ("verify_findings", "ok", 1))
        self.assertEqual(line["arguments"]["findings"]["items"], 4)
        self.assertNotIn("m_lastReported", json.dumps(line))
        self.assertNotIn("memcpy", json.dumps(line))

    def test_a_named_index_supplies_the_capitals_only_names(self):
        diff = "+++ b/core/src/x.cpp\n@@ -0,0 +1 @@\n+if (len > MAX_LEN) return;\n"
        (self.indexes / "base.json").write_text(json.dumps(
            {"types": [], "constants": [{"name": "SCONFIG"}]}), encoding="utf-8")
        finding = {"claim": "SCONFIG is ignored here", "file": "core/src/x.cpp",
                   "quote": "if (len > MAX_LEN) return;"}
        outcomes = [self.verify({"diff": diff, "findings": [finding], **extra})
                    .structured_content["results"][0]["outcome"]
                    for extra in ({}, {"index_name": "base.json"})]
        self.assertEqual(outcomes, ["kept", "link"])


class StatusTests(ServerTestCase):

    def test_unknown_and_malformed_ids_are_tool_errors(self):
        server = self.server()
        for rid in ("debate_20200101_000000_abcdef", "../../etc/passwd", "decision_x"):
            res = self.call(server, "get_decision", {"record_id": rid})
            self.assertTrue(res.is_error, rid)

    def test_a_review_lost_in_a_restart_is_reported_as_lost(self):
        rid = debate.new_debate_id()
        self.records.mkdir()
        marker_path(self.records, rid).write_text(json.dumps(
            {"record_id": rid, "state": "queued",
             "submitted_utc": "2026-11-19T20:00:00+00:00"}), encoding="utf-8")
        server = self.server()
        res = self.call(server, "get_decision", {"record_id": rid})
        self.assertFalse(res.is_error)
        self.assertEqual(res.structured_content["status"], "lost")
        self.assertIsNone(res.structured_content["final_verdict"])
        listed = self.call(server, "list_decisions", {}).structured_content["reviews"]
        self.assertEqual([(r["record_id"], r["status"]) for r in listed], [(rid, "lost")])

    def test_a_server_fault_is_failed_with_no_verdict(self):
        def broken(*_a, **_k):
            raise OSError("disk full")
        queue = ReviewQueue(self.records, {"name": "mcp"}, run=broken)
        server = self.server(queue)
        _, final = self.review(server, {"proposal": "p", "diff": DIFF})
        self.assertEqual(final["status"], "failed")
        self.assertIsNone(final["final_verdict"])
        self.assertIn("disk full", final["notes"][0])
        # A restart still answers it from the marker.
        res = self.call(self.server(), "get_decision", {"record_id": final["record_id"]})
        self.assertEqual(res.structured_content["status"], "failed")

    def test_the_marker_is_written_before_the_worker_can_take_the_job(self):
        # Written after, it overwrote a fast failure's marker, so a restart
        # reported the failed review as lost.
        queue = ReviewQueue(self.records, {"name": "mcp"}, run=lambda *a, **k: {})
        seen = []
        real_put = queue._pending.put_nowait

        def put(record_id):
            seen.append(marker_path(self.records, record_id).is_file())
            real_put(record_id)
        queue._pending.put_nowait = put
        queue.submit("p", DIFF)
        self.assertEqual(seen, [True])

    def test_a_review_finished_before_submit_returns_keeps_its_notes(self):
        # The worker can finish before review_diff describes the job.
        started = threading.Event()

        def instant(*_a, **_k):
            raise OSError("disk full")
        queue = ReviewQueue(self.records, {"name": "mcp"}, run=instant)
        real_submit = queue.submit

        def submit_then_finish(*a, **k):
            rid = real_submit(*a, **k)
            queue.join()
            started.set()
            return rid
        queue.submit = submit_then_finish
        res = self.call(self.server(queue), "review_diff", {"proposal": "p", "diff": DIFF})
        self.assertTrue(started.is_set())
        self.assertEqual(res.structured_content["status"], "failed")
        self.assertTrue(any("disk full" in n for n in res.structured_content["notes"]))

    def test_a_full_queue_answers_busy(self):
        release = threading.Event()
        started = threading.Event()

        def slow(*_a, debate_id, records_dir, on_progress, **_k):
            on_progress({"round": 1, "agent": "reviewer"})
            started.set()
            release.wait(10)
            raise OSError("stopped")
        queue = ReviewQueue(self.records, {"name": "mcp"}, max_pending=1, run=slow)
        server = self.server(queue, max_reviews_per_caller=5)  # the queue fills first
        args = {"proposal": "p", "diff": DIFF}
        first = self.call(server, "review_diff", args)
        self.assertTrue(started.wait(10))
        second = self.call(server, "review_diff", args)
        third = self.call(server, "review_diff", args)
        try:
            self.assertFalse(first.is_error)
            self.assertEqual(second.structured_content["status"], "queued")
            self.assertEqual(second.structured_content["queue_position"], 1)
            self.assertTrue(third.is_error)
            self.assertIn("busy", third.content[0].text)
            running = self.call(server, "get_decision",
                                {"record_id": first.structured_content["record_id"]})
            self.assertEqual(running.structured_content["status"], "running")
            self.assertEqual((running.structured_content["round"],
                              running.structured_content["agent"]), (1, "reviewer"))
        finally:
            release.set()
            queue.join()

    def test_waiting_sends_progress(self):
        release = threading.Event()
        progressed = []

        def stepping(*_a, debate_id, records_dir, on_progress, **_k):
            on_progress({"round": 1, "agent": "reviewer"})
            release.wait(10)
            on_progress({"round": 1, "agent": "auto_engineer"})
            raise OSError("stopped")
        queue = ReviewQueue(self.records, {"name": "mcp"}, run=stepping)
        server = self.server(queue)

        async def progress(value, total, message):
            progressed.append((value, total, message))
            release.set()

        async def go():
            async with Client(server) as c:
                sub = await c.call_tool("review_diff", {"proposal": "p", "diff": DIFF})
                return await c.call_tool(
                    "get_decision", {"record_id": sub.structured_content["record_id"],
                                     "wait_seconds": 20},
                    progress_callback=progress)
        try:
            # The first wait sees round 1's reviewer, then releases the engineer.
            with mock.patch.object(queue, "wait_for_change",
                                   wraps=queue.wait_for_change):
                res = run(go)
        finally:
            release.set()
            queue.join()
        self.assertEqual(res.structured_content["status"], "failed")
        self.assertTrue(progressed)
        self.assertEqual(progressed[0][1], 2 * debate.MAX_DEBATE_ROUNDS)


class ListAndResourceTests(ServerTestCase):

    def test_list_decisions_reports_verdicts_and_hashes_newest_first(self):
        server = self.server()
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN, REVIEWER_CLEAN, ENGINEER_CLEAN):
            _, a = self.review(server, {"proposal": "first", "diff": DIFF})
            _, b = self.review(server, {"proposal": "second", "diff": DIFF + "+int y;\n"})
        rows = self.call(server, "list_decisions", {}).structured_content["reviews"]
        self.assertEqual([r["record_id"] for r in rows], [b["record_id"], a["record_id"]])
        self.assertEqual(rows[0]["final_verdict"], "APPROVED_FOR_MERGE")
        self.assertEqual(rows[1]["diff_sha256"], debate.text_sha256(DIFF))
        limited = self.call(server, "list_decisions", {"limit": 1}).structured_content
        self.assertEqual(len(limited["reviews"]), 1)
        later = self.call(server, "list_decisions", {"since": "2999-01-01"}).structured_content
        self.assertEqual(later["reviews"], [])
        self.assertTrue(self.call(server, "list_decisions", {"since": "yesterday"}).is_error)

    def test_records_and_index_are_readable_resources(self):
        server = self.server()
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            _, final = self.review(server, {"proposal": "p", "diff": DIFF})

        async def go():
            async with Client(server) as c:
                rec = await c.read_resource(f"decision://{final['record_id']}")
                types = await c.read_resource("index://types")
                info = await c.read_resource("index://info")
                errors = []
                for uri in ("decision://debate_20200101_000000_abcdef",
                            "decision://..%2F..%2Fsecret"):
                    try:
                        await c.read_resource(uri)
                        errors.append(None)
                    except Exception as exc:  # the SDK raises MCPError
                        errors.append(type(exc).__name__)
                return rec, types, info, errors
        rec, types, info, errors = run(go)
        self.assertEqual(json.loads(rec.contents[0].text)["metadata"]["debate_id"],
                         final["record_id"])
        index = json.loads((REPO_ROOT / "repo_context.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(types.contents[0].text), index["types"])
        self.assertEqual(json.loads(info.contents[0].text)["source_commit"],
                         index["source_commit"])
        self.assertNotIn(None, errors)


class TaskToolTests(ServerTestCase):
    """The board's worker side over MCP (ADR-0006), on a temporary git
    repository with a worktree; the submitter posts through the board."""

    def setUp(self):
        super().setUp()
        self.projects, _, self.head, work = make_project(self.tmp)
        self.addCleanup(lambda: subprocess.run(
            ["git", "-C", str(self.tmp / "proj"), "worktree", "remove", "--force", str(work)],
            capture_output=True))
        self.mcp = self.server(projects_file=self.projects)
        self.board = Board(self.records / "tasks", self.projects)
        self.task_id = self.board.submit("second_read", "demo", self.head,
                                         {"findings": [TASK_FINDING]})["task_id"]

    def calls(self, *calls):
        async def go():
            async with Client(self.mcp) as c:
                return [await c.call_tool(tool, args) for tool, args in calls]
        return run(go)

    def test_a_worker_lists_claims_and_answers_and_the_submitter_reads_it(self):
        listed, claimed, answered = self.calls(
            ("list_tasks", {}), ("claim_task", {"task_id": self.task_id}),
            ("submit_result", {"task_id": self.task_id, "items": [TASK_ITEM]}))
        self.assertEqual(listed.structured_content["tasks"][0]["task_id"], self.task_id)
        self.assertFalse(claimed.is_error, claimed.content)
        self.assertEqual(claimed.structured_content["files"][0]["path"], "core/a.cpp")
        self.assertFalse(answered.is_error, answered.content)
        self.assertEqual(answered.structured_content["state"], "done")
        view = self.board.get(self.task_id)
        self.assertEqual(view["result"]["refuted"][0]["finding"], 0)
        self.assertEqual(json.loads((self.records / "tasks" / f"{self.task_id}.json")
                                    .read_text(encoding="utf-8"))["claim"]["worker"], "stdio")

    def test_a_refusal_and_a_malformed_item_are_tool_errors(self):
        early, bad = self.calls(
            ("submit_result", {"task_id": self.task_id, "items": [TASK_ITEM]}),
            ("submit_result", {"task_id": self.task_id,
                               "items": [dict(TASK_ITEM, verdict="maybe")]}))
        self.assertTrue(early.is_error)
        self.assertIn("not claimed", early.content[0].text)
        self.assertTrue(bad.is_error)
        self.assertEqual(self.board.list()[0]["state"], "open")


class StdioLaunchTests(unittest.TestCase):

    def test_the_server_starts_over_stdio_from_another_directory(self):
        # A client starts the server from its own working directory, and
        # any stray stdout line would corrupt the protocol.
        with tempfile.TemporaryDirectory() as tmp:
            params = StdioServerParameters(
                command=sys.executable, args=[str(REPO_ROOT / "mcp_server")], cwd=tmp,
                env={**os.environ, "LLMORCH_RECORDS_DIR": str(Path(tmp, "records"))})

            async def go():
                with anyio.fail_after(60):
                    async with Client(params) as c:
                        tools = await c.list_tools()
                        listed = await c.call_tool("list_decisions", {})
                        return {t.name for t in tools.tools}, listed
            tools, listed = anyio.run(go)
        self.assertIn("review_diff", tools)
        self.assertEqual(listed.structured_content["reviews"], [])


if __name__ == "__main__":
    unittest.main()
