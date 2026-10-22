"""Deterministic regression tests: no Ollama, no network, CI-safe.

Run from the repo root:
    python -m unittest discover -s tests -v

Each test pins a bug fixed on 2026-10-10 (see STATUS.md). The model is
replaced by a fake HTTP layer, so the real agent_client / adjudication /
debate code paths run end to end.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import agent_client  # noqa: E402
import debate  # noqa: E402
import repo_context  # noqa: E402
from adjudication import (demote_hedged_blockers, derive_verdict,  # noqa: E402
                          normalize_agent_output)
from agent_client import call_agent, failure_result  # noqa: E402
from eval_harness.bakeoff import tally  # noqa: E402
from eval_harness.probe import summarize  # noqa: E402
from file_metadata import identify_layer  # noqa: E402
from golden_tests import run_hedge_unit_tests, score_fixture  # noqa: E402
from reviewer_prompt import FAILURE_SENTINEL  # noqa: E402

REVIEWER_CLEAN = {"verdict": "approve", "blockers": [], "questions": [], "nits": []}
ENGINEER_CLEAN = {"verdict": "approve", "blockers": [], "concerns": [], "questions": []}


class FakeResp:
    """Minimal stand-in for an Ollama /api/chat response."""

    def __init__(self, content, done_reason="stop", thinking=None, **stats):
        if not isinstance(content, str):
            content = json.dumps(content)
        message = {"content": content}
        if thinking is not None:
            message["thinking"] = thinking
        self._body = {"message": message, "done_reason": done_reason, **stats}
        self.text = json.dumps(self._body)

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def fake_ollama(*replies):
    """Patch requests.post to return replies in order (FakeResp or
    exception instances). Returns the started patcher's mock."""
    seq = [r if isinstance(r, (FakeResp, Exception)) else FakeResp(r)
           for r in replies]
    p = mock.patch.object(agent_client.requests, "post", side_effect=seq)
    return p


class NoSleep(unittest.TestCase):
    def setUp(self):
        sleeper = mock.patch.object(agent_client.time, "sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)


# ============ adjudication ============

class SchemaValidationTests(unittest.TestCase):
    def test_wrong_keys_are_a_failure_not_an_empty_review(self):
        out, err = normalize_agent_output(
            {"verdict": "reject", "issues": ["overflow at line 4"]}, "reviewer")
        self.assertIsNone(out)
        self.assertIn("missing required keys", err)

    def test_nested_reply_is_a_failure(self):
        out, err = normalize_agent_output(
            {"review": {"verdict": "reject", "blockers": ["x"]}}, "reviewer")
        self.assertIsNone(out)

    def test_non_object_reply_is_a_failure(self):
        for raw in (["x"], "text", 3, None):
            out, err = normalize_agent_output(raw, "engineer")
            self.assertIsNone(out, raw)
            self.assertIn("expected an object", err)

    def test_object_items_keep_their_line_citation(self):
        out, err = normalize_agent_output(
            {"blockers": [{"line": 4, "rule": "CAN-FD", "issue": "overflow"}],
             "questions": []}, "reviewer")
        self.assertIsNone(err)
        self.assertEqual(out["blockers"], ["line: 4; rule: CAN-FD; issue: overflow"])

    def test_null_and_bare_string_arrays_are_coerced(self):
        out, err = normalize_agent_output(
            {"blockers": "memcpy overflows buf[8] at line 4", "concerns": None,
             "questions": []}, "engineer")
        self.assertIsNone(err)
        self.assertEqual(out["blockers"], ["memcpy overflows buf[8] at line 4"])
        self.assertEqual(out["concerns"], [])

    def test_placeholder_items_are_dropped(self):
        out, _ = normalize_agent_output(
            {"blockers": ["None", "n/a", "", "None."], "questions": []}, "reviewer")
        self.assertEqual(out["blockers"], [])

    def test_non_list_array_is_a_failure(self):
        out, err = normalize_agent_output({"blockers": 3, "questions": []}, "reviewer")
        self.assertIsNone(out)


class VerdictTests(unittest.TestCase):
    def test_schema_invalid_output_fails_closed(self):
        self.assertEqual(derive_verdict({"verdict": "reject", "issues": ["x"]}), "reject")
        self.assertEqual(derive_verdict({"verdict": "approve"}), "reject")
        self.assertEqual(derive_verdict(["x"]), "reject")
        self.assertEqual(derive_verdict(dict(FAILURE_SENTINEL)), "reject")

    def test_well_formed_outputs_unchanged(self):
        self.assertEqual(derive_verdict(REVIEWER_CLEAN), "approve")
        self.assertEqual(derive_verdict({**REVIEWER_CLEAN, "questions": ["q"]}), "conditional")
        self.assertEqual(derive_verdict({**REVIEWER_CLEAN, "blockers": ["b"]}), "reject")
        self.assertEqual(derive_verdict({**ENGINEER_CLEAN, "concerns": ["c"]}, "concerns"),
                         "conditional")
        self.assertEqual(derive_verdict({**ENGINEER_CLEAN, "questions": ["q"]}, "concerns"),
                         "conditional")

    def test_hedge_units_still_pass(self):
        results = run_hedge_unit_tests()
        failed = [r["test_name"] for r in results if not r["test_passed"]]
        self.assertEqual(failed, [])
        self.assertEqual(len(results), 7)

    def test_demotion_passes_non_dicts_through(self):
        self.assertEqual(demote_hedged_blockers(["x"]), ["x"])


# ============ layer detection ============

class LayerTests(unittest.TestCase):
    def test_identify_layer(self):
        cases = {
            "core/src/frame_decode.cpp": "core",
            "// core/src/frame_decode.cpp": "core",
            "// core/include/qttune/session.h (public C ABI header)": "core",
            "// core/src/can_bridge.cpp": "core",
            "app/qttunebridge.cpp": "bridge",
            "tests/test_bridge.cpp": "bridge",
            "app/qml/Main.qml": "app",
            "hardcore/x.cpp": "unknown",
            "": "unknown",
        }
        for path, layer in cases.items():
            self.assertEqual(identify_layer(path), layer, path)

    def test_extract_file_path(self):
        ex = debate.extract_file_path
        self.assertEqual(ex("", "// SPDX-License-Identifier: MIT\n// core/src/x.cpp\n"),
                         "core/src/x.cpp")
        self.assertEqual(ex("", "// File/layer: core/include/qttune/core.h | C ABI\n"),
                         "core/include/qttune/core.h")
        self.assertEqual(ex("+++ b/app/qttunebridge.cpp\n", "// core/src/x.cpp"),
                         "app/qttunebridge.cpp")
        self.assertEqual(ex("", "// just a comment\nint x;\n"), "")


# ============ agent_client ============

class AgentClientTests(NoSleep):
    validate = staticmethod(lambda raw: normalize_agent_output(raw, "reviewer"))

    def test_schema_violation_is_retried_with_correction(self):
        with fake_ollama({"verdict": "reject", "issues": ["x"]}, REVIEWER_CLEAN) as post:
            out = call_agent("m", "sys", "t", 0.7, validate=self.validate)
        self.assertEqual(out["blockers"], [])
        self.assertNotEqual(out.get("verdict"), "PARSE_FAILURE")
        retry_messages = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertIn("missing required keys", retry_messages[-1]["content"])

    def test_persistent_schema_violation_fails_closed_with_reason(self):
        bad = {"verdict": "approve", "review": {}}
        with fake_ollama(bad, bad, bad):
            out = call_agent("m", "sys", "t", 0.7, validate=self.validate)
        self.assertEqual(out["verdict"], "PARSE_FAILURE")
        self.assertIn("schema violation", out["failure_reason"])

    def test_timeout_reason_and_no_sleep_after_last_attempt(self):
        t = requests.exceptions.Timeout()
        with fake_ollama(t, t, t):
            out = call_agent("m", "sys", "t", 0.7)
        self.assertTrue(out["failure_reason"].startswith("timeout"))
        self.assertEqual(self.sleep.call_count, 2)

    def test_truncated_output_points_at_num_ctx(self):
        cut = FakeResp('{"verdict": "reject", "blockers": ["unterminated',
                       done_reason="length", prompt_eval_count=9000,
                       eval_count=7384)
        with fake_ollama(cut, cut, cut):
            out = call_agent("m", "sys", "t", 0.7)
        self.assertIn("NUM_CTX", out["failure_reason"])
        self.assertIn("9000 prompt + 7384 output tokens", out["failure_reason"])

    # ---- telemetry (code review 2026-10-21, finding 8) ----

    def test_every_attempt_is_recorded_successful_or_not(self):
        calls = []
        bad = FakeResp({"verdict": "reject", "issues": ["x"]},
                       prompt_eval_count=120, eval_count=30)
        good = FakeResp(REVIEWER_CLEAN, prompt_eval_count=140, eval_count=25)
        with fake_ollama(requests.exceptions.Timeout(), bad, good):
            out = call_agent("m", "sys", "t", 0.7, validate=self.validate,
                             telemetry=calls)
        self.assertEqual(out["blockers"], [])
        self.assertEqual([c["attempt"] for c in calls], [0, 1, 2])
        self.assertEqual([c["temperature"] for c in calls],
                         [0.7, agent_client.TEMPERATURE_RETRY,
                          agent_client.TEMPERATURE_RETRY])
        timeout, schema, ok = calls
        self.assertIsNone(timeout["prompt_eval_count"])
        self.assertTrue(timeout["outcome"].startswith("timeout"))
        self.assertEqual((schema["prompt_eval_count"], schema["eval_count"]), (120, 30))
        self.assertIn("schema violation", schema["outcome"])
        self.assertEqual((ok["prompt_eval_count"], ok["done_reason"], ok["outcome"]),
                         (140, "stop", "ok"))
        # the retry carries the corrective message, so its prompt is longer
        self.assertEqual(schema["prompt_chars"], len("sys") + len("t"))
        self.assertGreater(ok["prompt_chars"], schema["prompt_chars"])

    def test_runaway_keeps_the_tail_of_its_thinking(self):
        calls = []
        loop = "Wait, let me re-check the frame counter. " * 300
        runaway = FakeResp("", done_reason="length", thinking=loop,
                           prompt_eval_count=10075, eval_count=14501)
        good = FakeResp(REVIEWER_CLEAN, thinking="Short check.")
        with fake_ollama(runaway, good):
            call_agent("m", "sys", "t", 0.05, validate=self.validate,
                       telemetry=calls)
        failed, ok = calls
        self.assertEqual(failed["thinking_chars"], len(loop))
        self.assertEqual(failed["content_chars"], 0)
        self.assertEqual(failed["thinking_tail"],
                         loop[-agent_client.FAILURE_TAIL_CHARS:])
        self.assertEqual(failed["content_tail"], "")
        # successful attempts keep sizes only, never the text
        self.assertEqual(ok["thinking_chars"], len("Short check."))
        self.assertNotIn("thinking_tail", ok)

    def test_every_request_caps_output(self):
        with fake_ollama(REVIEWER_CLEAN) as post:
            call_agent("m", "sys", "t", 0.7, validate=self.validate)
        options = post.call_args.kwargs["json"]["options"]
        self.assertEqual(options["num_predict"], agent_client.NUM_PREDICT)
        self.assertLess(options["num_predict"], options["num_ctx"])

    def test_telemetry_is_optional(self):
        with fake_ollama(REVIEWER_CLEAN):
            out = call_agent("m", "sys", "t", 0.7, validate=self.validate)
        self.assertEqual(out["blockers"], [])

    def test_failure_results_do_not_share_lists(self):
        a = failure_result("x")
        a["blockers"].append("mutated")
        self.assertEqual(FAILURE_SENTINEL["blockers"], [])
        self.assertEqual(failure_result("y")["blockers"], [])


# ============ debate ============

class DebateTests(NoSleep):
    def setUp(self):
        super().setUp()
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)  # decision records land here

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def record(self, result):
        return json.loads(Path(result["decision_record_path"]).read_text(encoding="utf-8"))

    def test_object_blockers_and_null_concerns_do_not_crash(self):
        rev = {"verdict": "reject", "questions": [],
               "blockers": [{"line": 4, "rule": "buffer", "issue": "overflow"}]}
        eng = {"verdict": "approve", "blockers": [], "concerns": None, "questions": []}
        with fake_ollama(rev, eng, rev, eng, rev, eng):
            result = debate.run_debate("p", "+++ b/core/src/x.cpp\n", "")
        self.assertEqual(result["final_verdict"],
                         "MAX_ROUNDS_EXCEEDED - MANUAL_REVIEW_REQUIRED")
        rec = self.record(result)
        self.assertIn("line: 4; rule: buffer", rec["inputs"]["proposal"])

    def test_schema_invalid_agents_never_approve(self):
        bad = {"verdict": "approve", "summary": "looks fine"}
        with fake_ollama(bad, bad, bad) as post:
            result = debate.run_debate("p", "", "")
        self.assertEqual(result["final_verdict"], debate.AGENT_FAILURE_VERDICT)
        self.assertEqual(result["rounds_completed"], 1)
        self.assertEqual(post.call_count, 3)  # engineer skipped once reviewer failed
        self.assertIn("schema violation", result["agent_failures"][0])

    def test_server_down_is_reported_as_agent_failure(self):
        err = requests.exceptions.ConnectionError("refused")
        with fake_ollama(err, err, err):
            result = debate.run_debate("p", "", "")
        self.assertEqual(result["final_verdict"], debate.AGENT_FAILURE_VERDICT)
        self.assertIn("request failed", result["agent_failures"][0])

    def test_clean_round_approves_and_record_has_provenance(self):
        with fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN):
            result = debate.run_debate("orig", "+++ b/core/src/x.cpp\n", "",
                                       header_artifact=False)
        self.assertEqual(result["final_verdict"], "APPROVED_FOR_MERGE")
        rec = self.record(result)
        self.assertEqual(rec["inputs"]["original_proposal"], "orig")
        self.assertEqual(rec["inputs"]["layer"], "core")
        self.assertEqual(len(rec["inputs"]["diff_sha256"]), 64)
        self.assertEqual(len(rec["metadata"]["prompt_fingerprint"]), 16)
        self.assertEqual(rec["outputs"]["agent_failures"], [])

    # ---- retrieval inside the debate (code review 2026-10-21, finding 2) ----

    def write_index(self, files):
        path = Path(self._tmp.name) / "index.json"
        path.write_text(json.dumps({"files": files, "types": [], "constants": [],
                                    "callsites": []}), encoding="utf-8")
        return path

    def test_committed_index_loads_from_any_working_directory(self):
        # setUp moved the CWD into a temp dir; the index must still load.
        index = debate._load_repo_index()
        self.assertNotIn("_load_error", index)
        self.assertTrue(index["files"])

    def test_pack_reaches_the_transcript_and_the_record(self):
        path = self.write_index([{"path": "app/x.cpp", "layer": "bridge",
                                  "purpose": "Sentinel purpose for retrieval."}])
        with mock.patch.object(debate, "CONTEXT_PATH", path), \
                fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN) as post:
            result = debate.run_debate("p", "+++ b/app/x.cpp\n+int y;\n", "")
        transcript = post.call_args_list[0].kwargs["json"]["messages"][1]["content"]
        self.assertIn("REPO CONTEXT", transcript)
        self.assertIn("Sentinel purpose for retrieval.", transcript)
        self.assertNotIn("retrieval_error", result)
        self.assertIsNone(self.record(result)["metadata"]["repo_context_pack"]["error"])

    def test_missing_index_warns_and_is_reported(self):
        missing = Path(self._tmp.name) / "nope.json"
        stderr = io.StringIO()
        with mock.patch.object(debate, "CONTEXT_PATH", missing), \
                contextlib.redirect_stderr(stderr), \
                fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN) as post:
            result = debate.run_debate("p", "+++ b/app/x.cpp\n", "")
        self.assertIn("FileNotFoundError", result["retrieval_error"])
        self.assertIn("WARNING: repo context retrieval unavailable", stderr.getvalue())
        transcript = post.call_args_list[0].kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("REPO CONTEXT", transcript)

    # ---- record provenance and degradation (code review 2026-10-21, findings 5, 6, 8) ----

    def debate_with_purpose(self, purpose):
        path = self.write_index([{"path": "app/x.cpp", "layer": "bridge",
                                  "purpose": purpose}])
        with mock.patch.object(debate, "CONTEXT_PATH", path), \
                fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN) as post:
            result = debate.run_debate("p", "+++ b/app/x.cpp\n+int y;\n", "")
        transcript = post.call_args_list[0].kwargs["json"]["messages"][1]["content"]
        return self.record(result), transcript

    def test_record_keeps_the_exact_pack_the_agents_saw(self):
        rec, transcript = self.debate_with_purpose("Sentinel purpose for retrieval.")
        pack = rec["metadata"]["repo_context_pack"]
        self.assertIn(pack["text"], transcript)
        self.assertEqual(pack["sha256"], debate._sha256(pack["text"]))
        self.assertEqual(pack["used"], len(pack["text"]))
        self.assertEqual(pack["format_version"], repo_context.PACK_FORMAT_VERSION)
        self.assertIn("index_version", pack)

    def test_fingerprint_depends_on_templates_not_on_the_pack_text(self):
        rec_a, _ = self.debate_with_purpose("First purpose for the fingerprint.")
        rec_b, _ = self.debate_with_purpose("Second, different purpose text.")
        a, b = rec_a["metadata"], rec_b["metadata"]
        self.assertNotEqual(a["repo_context_pack"]["sha256"],
                            b["repo_context_pack"]["sha256"])
        self.assertEqual(a["prompt_fingerprint"], b["prompt_fingerprint"])

    def test_malformed_index_degrades_instead_of_crashing(self):
        path = Path(self._tmp.name) / "bad.json"
        path.write_text(json.dumps({"files": [{"path": "app/x.cpp"}],
                                    "types": [{"kind": "struct"}]}),  # no "name"
                        encoding="utf-8")
        with mock.patch.object(debate, "CONTEXT_PATH", path), \
                contextlib.redirect_stderr(io.StringIO()), \
                fake_ollama(REVIEWER_CLEAN, ENGINEER_CLEAN) as post:
            result = debate.run_debate("p", "+++ b/app/x.cpp\n", "")
        self.assertEqual(result["final_verdict"], "APPROVED_FOR_MERGE")
        self.assertIn("malformed index: KeyError", result["retrieval_error"])
        transcript = post.call_args_list[0].kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("REPO CONTEXT", transcript)

    def test_rounds_record_per_attempt_telemetry(self):
        with fake_ollama(FakeResp(REVIEWER_CLEAN, prompt_eval_count=900, eval_count=40),
                         FakeResp(ENGINEER_CLEAN, prompt_eval_count=800, eval_count=20)):
            result = debate.run_debate("p", "+++ b/core/src/x.cpp\n", "")
        rec = self.record(result)
        self.assertEqual(rec["metadata"]["num_predict"], debate.NUM_PREDICT)
        telemetry = rec["outputs"]["round_history"][0]["telemetry"]
        self.assertEqual(telemetry["reviewer"][0]["prompt_eval_count"], 900)
        self.assertEqual(telemetry["auto_engineer"][0]["eval_count"], 20)

    def test_skipped_engineer_has_no_telemetry(self):
        bad = {"verdict": "approve", "summary": "looks fine"}
        with fake_ollama(bad, bad, bad):
            result = debate.run_debate("p", "", "")
        telemetry = self.record(result)["outputs"]["round_history"][0]["telemetry"]
        self.assertEqual(len(telemetry["reviewer"]), 3)
        self.assertEqual(telemetry["auto_engineer"], [])


# ============ eval scoring ============

class EvalScoringTests(unittest.TestCase):
    def test_golden_parse_failure_never_passes(self):
        failed = failure_result("x")
        self.assertFalse(score_fixture(failed, expected_to_block=False)["test_passed"])
        self.assertFalse(score_fixture(failed, expected_to_block=True)["test_passed"])
        self.assertTrue(score_fixture(REVIEWER_CLEAN, False)["test_passed"])
        self.assertTrue(score_fixture({**REVIEWER_CLEAN, "blockers": ["b"]}, True)["test_passed"])

    @staticmethod
    def run_(verdict, blockers=()):
        return {"verdict": verdict, "blockers": list(blockers),
                "inflated": verdict == "reject" and not blockers,
                "timed_out": verdict == "TIMEOUT"}

    def test_probe_all_failures_is_not_clean(self):
        self.assertEqual(summarize([self.run_("PARSE_FAILURE")] * 5)["classification"],
                         "NO_DATA")
        self.assertEqual(summarize([self.run_("TIMEOUT")] * 5)["classification"], "NO_DATA")
        self.assertEqual(summarize([self.run_("conditional")] * 5)["classification"], "CLEAN")
        mixed = [self.run_("conditional")] * 4 + [self.run_("PARSE_FAILURE")]
        self.assertEqual(summarize(mixed)["classification"], "BORDERLINE")

    def test_bakeoff_failed_bug_case_is_a_miss(self):
        s = tally([(True, None, True), (True, "parse", False), (True, "timeout", False),
                   (False, None, False), (False, "parse", False)])
        self.assertEqual(s["tp"] + s["fn"], s["bug_total"])
        self.assertEqual((s["tp"], s["fn"], s["bug_total"]), (1, 2, 3))
        self.assertEqual(s["fp"] + s["clean_ok"] + s["clean_failed"], s["clean_total"])
        self.assertEqual((s["json_fails"], s["timeouts"]), (2, 1))


# ============ repo_context ============

QTTUNE_LIKE_HEADER = """
/* Forward-declared opaque handle types */
typedef struct qttune_session qttune_session_t;

/* Frame structure - POD only */
typedef struct qttune_frame {
    uint64_t timestamp_us;    /* Microseconds */
    uint32_t channel_id;      /* Logical channel */
    uint8_t data[64];         /* Max CAN-FD payload size */
    uint8_t data_length;      /* Actual bytes used (0-64) */
} qttune_frame_t;

/* Callback function signature - called from transport thread */
typedef void (*qttune_frame_callback_t)(
    const qttune_frame_t* frame,
    void* user_data
);

typedef enum {
    QT_OK = 0,
    QT_ERR_NULL_ARGUMENT = 1   /* trailing comment */
} qttune_status_t;
"""


class RepoContextTests(unittest.TestCase):
    def types(self, text):
        return {t["name"]: t for t in repo_context.harvest_typedefs(text)}

    def test_typedef_kinds_members_and_docs(self):
        t = self.types(QTTUNE_LIKE_HEADER)
        self.assertEqual(t["qttune_session_t"]["kind"], "opaque")
        self.assertEqual(t["qttune_frame_t"]["members"],
                         ["timestamp_us", "channel_id", "data", "data_length"])
        cb = t["qttune_frame_callback_t"]
        self.assertEqual(cb["kind"], "function_pointer")
        self.assertIn("called from transport thread", cb["doc"])
        self.assertEqual(t["qttune_status_t"]["values"],
                         {"QT_OK": "0", "QT_ERR_NULL_ARGUMENT": "1"})

    def test_consecutive_members_are_all_found(self):
        t = self.types("typedef struct { int a; int b; int c; int d; } t;")
        self.assertEqual(t["t"]["members"], ["a", "b", "c", "d"])

    def test_nested_aggregate_keeps_outer_name(self):
        t = self.types("typedef struct { union { int i; float f; } u; int n; } outer_t;")
        self.assertEqual(list(t), ["outer_t"])
        self.assertEqual(t["outer_t"]["members"], ["u", "n"])

    def test_constants_defines_hex_and_no_locals(self):
        src = ("#define MAX_DLC 64\n"
               "static const uint32_t kMask = 0x7FF;\n"
               "static constexpr int MaxFrames = 10000; // cap\n"
               "// constexpr int kDead = 1;\n"
               "void f() {\n    int count = 0;\n}\n")
        got = {c["name"]: c["value"] for c in repo_context.harvest_constants(src, "f")}
        self.assertEqual(got, {"MAX_DLC": "64", "kMask": "0x7FF", "MaxFrames": "10000"})

    def test_llm_failure_yields_no_purpose(self):
        with mock.patch.object(repo_context, "call_agent",
                               return_value=failure_result("timeout")):
            self.assertIsNone(repo_context.llm_purpose("m", "core/x.h", "int x;"))

    def test_purpose_validator_reads_the_purpose_key(self):
        ok, err = repo_context._validate_purpose(
            {"file": "core/include/qttune/core.h", "purpose": "Defines the public C ABI."})
        self.assertEqual(ok["purpose"], "Defines the public C ABI.")
        bad, err = repo_context._validate_purpose({"file": "core/include/qttune/core.h"})
        self.assertIsNone(bad)

    def test_checkout_under_a_build_directory_still_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "build" / "repo"
            (repo / "core").mkdir(parents=True)
            (repo / "core" / "x.h").write_text("#define LIMIT 8\n", encoding="utf-8")
            (repo / "build").mkdir()
            (repo / "build" / "gen.h").write_text("#define GEN 1\n", encoding="utf-8")
            idx = repo_context.build_index(str(repo), use_llm=False)
        self.assertEqual([f["path"] for f in idx["files"]], ["core/x.h"])
        self.assertIsNone(idx["source_commit"])  # not a git checkout

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_index_records_the_commit_it_describes(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(["git", "init", "-q", tmp], check=True)
            Path(tmp, "x.h").write_text("#define LIMIT 8\n", encoding="utf-8")
            subprocess.run(git + ["add", "x.h"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "c"], check=True)
            head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True,
                                  text=True, check=True).stdout.strip()
            clean = repo_context.build_index(tmp, use_llm=False)
            Path(tmp, "x.h").write_text("#define LIMIT 9\n", encoding="utf-8")
            dirty = repo_context.build_index(tmp, use_llm=False)
        self.assertEqual((clean["source_commit"], clean["source_dirty"]), (head, False))
        self.assertEqual((dirty["source_commit"], dirty["source_dirty"]), (head, True))


# ============ CLI ============

class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "orchestrator.py", *args],
                              cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=60)

    def test_modes_are_mutually_exclusive(self):
        r = self.run_cli("--golden", "--proposal", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not allowed with", r.stderr)

    def test_diff_requires_proposal(self):
        r = self.run_cli("--golden", "--diff", "x.diff")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
