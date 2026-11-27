"""The task board (ADR-0006): projects, claims, the quote check on a
worker's answer, the retry, the denylist and the CLI, on a temporary git
repository with a worktree. No model, no network.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import adjudication  # noqa: E402
from tasks import __main__ as cli  # noqa: E402
from tasks.board import Board, TaskError  # noqa: E402
from tasks.projects import ProjectError, _frontmatter_paths, _glob, load_project  # noqa: E402

BASE = "int count = 0;\nvoid tick() { count++; }\n"
CHANGED = "int count = 0;\nvoid tick() { if (count < 10) count++; }\n"
RULE = '---\npaths:\n  - "core/**"\n---\n# Core\nEvery counter is bounded by its limit check.\n'


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "core.autocrlf=false", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_project(tmp: Path):
    """A repository whose rules and denylist are git-ignored, a worktree at
    a second commit, and a projects.json naming it. (projects file, base
    commit, work commit, worktree path)"""
    root = tmp / "proj"
    (root / "core").mkdir(parents=True)
    (root / "rules").mkdir()
    (root / "local").mkdir()
    (root / ".gitignore").write_text("rules/\nlocal/\n", encoding="utf-8")
    (root / "core" / "a.cpp").write_text(BASE, encoding="utf-8")
    (root / "README.md").write_text("A counter.\n", encoding="utf-8")
    (root / "rules" / "core.md").write_text(RULE, encoding="utf-8")
    (root / "local" / "deny.txt").write_text("# private\n\\bzanzibar\\b\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    work = tmp / "wt"
    _git(root, "worktree", "add", "-q", "-b", "feat/x", str(work))
    (work / "core" / "a.cpp").write_text(CHANGED, encoding="utf-8")
    _git(work, "commit", "-q", "-am", "bound the counter")
    head = _git(work, "rev-parse", "HEAD")
    projects = tmp / "projects.json"
    projects.write_text(json.dumps({"projects": {"demo": {
        "root": str(root), "rules": "rules", "always": ["README.md"],
        "denylist": "local/deny.txt", "never": ["local/"]}}}), encoding="utf-8")
    return projects, base, head, work


FINDING = {"claim": "tick() increments count with no bound", "file": "core/a.cpp"}


def item(**kw):
    out = {"finding": 0, "verdict": "refuted", "file": "core/a.cpp",
           "quote": "void tick() { if (count < 10) count++; }",
           "reason": "tick() checks count against 10 before the increment."}
    out.update(kw)
    return out


class BoardTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.projects, self.base, self.head, self.work = make_project(self.tmp)
        self.board = Board(self.tmp / "records" / "tasks", self.projects)
        self.addCleanup(self._remove_worktree)

    def _remove_worktree(self):
        with contextlib.suppress(Exception):
            _git(self.tmp / "proj", "worktree", "remove", "--force", str(self.work))

    def post(self, findings=None, commit=None):
        return self.board.submit("second_read", "demo", commit or self.head,
                                 {"findings": findings or [FINDING]})["task_id"]

    def record(self, task_id):
        return json.loads((self.board.dir / f"{task_id}.json").read_text(encoding="utf-8"))


class ProjectTests(BoardTestCase):

    def test_globs_follow_the_rules_paths_syntax(self):
        self.assertTrue(_glob("core/**").fullmatch("core/src/x.cpp"))
        self.assertTrue(_glob("app/x.*").fullmatch("app/x.cpp"))
        self.assertFalse(_glob("app/x.*").fullmatch("app/sub/x.cpp"))
        self.assertTrue(_glob("**/*.md").fullmatch("README.md"))
        self.assertEqual(_frontmatter_paths(RULE), ["core/**"])
        self.assertEqual(_frontmatter_paths("# no frontmatter\n"), [])

    def test_a_task_lists_the_cited_files_the_always_files_and_the_matching_rules(self):
        out = self.board.submit("second_read", "demo", self.head, {"findings": [FINDING]})
        self.assertEqual(out["files"], ["core/a.cpp", "README.md", "rules/core.md"])
        self.assertEqual(self.record(out["task_id"])["commit"], self.head)

    def test_submissions_a_task_cannot_take_are_refused(self):
        cases = [
            ({"findings": []}, "non-empty list"),
            ({"findings": [{"claim": "x", "file": "local/deny.txt"}]}, "never list"),
            ({"findings": [{"claim": "x", "file": "../etc/passwd"}]}, "inside the project"),
            ({"findings": [{"claim": "Zanzibar is named", "file": "core/a.cpp"}]}, "denylist"),
        ]
        for payload, why in cases:
            with self.subTest(why=why), self.assertRaisesRegex(TaskError, why):
                self.board.submit("second_read", "demo", self.head, payload)
        with self.assertRaisesRegex(TaskError, "not a commit"):
            self.board.submit("second_read", "demo", "HEAD~1", {"findings": [FINDING]})
        with self.assertRaisesRegex(TaskError, "no project"):
            self.board.submit("second_read", "nope", self.head, {"findings": [FINDING]})
        self.assertEqual(self.board.list(), [])

    def test_a_missing_denylist_refuses_every_task(self):
        (self.tmp / "proj" / "local" / "deny.txt").unlink()
        with self.assertRaisesRegex(TaskError, "denylist is missing"):
            self.post()

    def test_load_project_names_what_is_missing(self):
        with self.assertRaisesRegex(ProjectError, "no projects.json"):
            load_project("demo", self.tmp / "projects.json.absent")


class ClaimTests(BoardTestCase):

    def test_a_claim_names_the_worktree_at_the_commit_and_hashes_ignored_files(self):
        bundle = self.board.claim(self.post(), "lumo")
        self.assertEqual(Path(bundle["checkout"]).resolve(), self.work.resolve())
        reads = {f["path"]: Path(f["read_from"]).resolve() for f in bundle["files"]}
        self.assertEqual(reads["core/a.cpp"], (self.work / "core" / "a.cpp").resolve())
        self.assertEqual(reads["rules/core.md"],
                         (self.tmp / "proj" / "rules" / "core.md").resolve())
        claim = self.record(bundle["task_id"])["claim"]
        self.assertEqual(set(claim["working_hashes"]), {"rules/core.md"})
        self.assertIn("second read", bundle["instructions"].lower())
        self.assertEqual(bundle["findings"][0]["index"], 0)

    def test_no_checkout_at_the_commit_refuses_the_claim_and_leaves_the_task_open(self):
        at_base = self.post(commit=self.base)
        self.board.claim(at_base, "lumo")  # the main clone is at the base
        _git(self.work, "checkout", "-q", "--detach", self.base)
        task_id = self.post()
        with self.assertRaisesRegex(TaskError, "no checkout"):
            self.board.claim(task_id, "lumo")
        self.assertEqual(self.record(task_id)["state"], "open")

    def test_uncommitted_changes_to_a_listed_file_refuse_the_claim(self):
        (self.work / "core" / "a.cpp").write_text(BASE, encoding="utf-8")
        with self.assertRaisesRegex(TaskError, "changes to core/a.cpp"):
            self.board.claim(self.post(), "lumo")

    def test_only_one_worker_holds_a_claim(self):
        task_id = self.post()
        first = self.board.claim(task_id, "lumo")
        self.assertEqual(self.board.claim(task_id, "lumo")["task_id"], first["task_id"])
        with self.assertRaisesRegex(TaskError, "another worker"):
            self.board.claim(task_id, "other")

    def test_concurrent_claims_give_the_task_to_one_worker(self):
        task_id = self.post()
        results = []

        def claim(worker):
            try:
                self.board.claim(task_id, worker)
                results.append(worker)
            except TaskError:
                pass
        threads = [threading.Thread(target=claim, args=(f"w{i}",)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 1)
        self.assertEqual(self.record(task_id)["claim"]["worker"], results[0])


class AnswerTests(BoardTestCase):

    def claimed(self, findings=None):
        task_id = self.post(findings)
        self.board.claim(task_id, "lumo")
        return task_id

    def test_a_quoted_answer_is_done_and_only_checked_items_come_back(self):
        task_id = self.claimed([FINDING, {"claim": "README is empty", "file": "README.md"}])
        out = self.board.submit_result(task_id, "lumo", [
            item(), item(finding=1, verdict="unclear", file="", quote="", reason="")])
        self.assertEqual(out["state"], "done")
        self.assertEqual([i["finding"] for i in out["result"]["refuted"]], [0])
        self.assertEqual([i["finding"] for i in out["result"]["unclear"]], [1])
        self.assertEqual(out["result"]["unverified"], [])

    def test_a_quote_of_the_old_code_comes_back_once_then_is_unverified(self):
        # The base's line is not in the file at the task's commit.
        task_id = self.claimed()
        stale = item(verdict="supported", quote="void tick() { count++; }",
                     reason="tick() increments count with no check.")
        retry = self.board.submit_result(task_id, "lumo", [stale])
        self.assertEqual(retry["status"], "retry")
        self.assertIn("not in core/a.cpp", retry["rejected"][0]["why"])
        self.assertEqual(self.board.claim(task_id, "lumo")["rejected"], retry["rejected"])
        out = self.board.submit_result(task_id, "lumo", [stale])
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["result"]["supported"], [])
        self.assertEqual(out["result"]["unverified"][0]["finding"], 0)

    def test_a_retry_fixes_the_rejected_item_and_keeps_the_passed_ones(self):
        task_id = self.claimed([FINDING, dict(FINDING, claim="count is never reset")])
        first = self.board.submit_result(task_id, "lumo", [
            item(), item(finding=1, verdict="supported", reason="It might never be reset.")])
        self.assertEqual([r["finding"] for r in first["rejected"]], [1])
        self.assertEqual(first["rejected"][0]["why"], "the reason hedges")
        out = self.board.submit_result(task_id, "lumo", [
            item(finding=1, verdict="supported", quote="int count = 0;",
                 reason="count is set to 0 only where it is declared.")])
        self.assertEqual([i["finding"] for i in out["result"]["refuted"]], [0])
        self.assertEqual([i["finding"] for i in out["result"]["supported"]], [1])

    def test_quotes_must_come_from_a_listed_file(self):
        task_id = self.claimed()
        retry = self.board.submit_result(task_id, "lumo", [item(file="core/b.cpp")])
        self.assertIn("not one of the task's files", retry["rejected"][0]["why"])

    def test_a_quote_from_an_ignored_rule_passes_until_the_rule_changes(self):
        task_id = self.claimed([FINDING, dict(FINDING, claim="the rule allows unbounded counters")])
        rule_item = item(finding=1, file="rules/core.md",
                         quote="Every counter is bounded by its limit check.",
                         reason="The core rule requires a bound on every counter.")
        (self.tmp / "proj" / "rules" / "core.md").write_text(RULE + "Edited.\n",
                                                             encoding="utf-8")
        retry = self.board.submit_result(task_id, "lumo", [item(), rule_item])
        self.assertIn("changed since the claim", retry["rejected"][0]["why"])
        (self.tmp / "proj" / "rules" / "core.md").write_text(RULE, encoding="utf-8")
        out = self.board.submit_result(task_id, "lumo", [rule_item])
        self.assertEqual([i["finding"] for i in out["result"]["refuted"]], [0, 1])

    def test_an_answer_with_no_usable_item_twice_fails_the_task(self):
        task_id = self.claimed()
        self.assertEqual(self.board.submit_result(task_id, "lumo", "nope")["status"], "retry")
        out = self.board.submit_result(task_id, "lumo", [{"verdict": "maybe"}])
        self.assertEqual(out["state"], "failed")
        self.assertNotIn("result", out)

    def test_a_result_matching_the_denylist_fails_without_a_result(self):
        task_id = self.claimed()
        out = self.board.submit_result(task_id, "lumo", [item(
            reason="tick() checks count against 10 before the increment, unlike Zanzibar.")])
        self.assertEqual(out["state"], "failed")
        self.assertIn("denylist", out["failure"])
        self.assertIsNone(self.record(task_id)["result"])

    def test_only_the_claiming_worker_answers(self):
        task_id = self.claimed()
        with self.assertRaisesRegex(TaskError, "not claimed by this worker"):
            self.board.submit_result(task_id, "other", [item()])

    def test_the_record_counts_what_the_submitter_spent(self):
        task_id = self.claimed()
        self.board.submit_result(task_id, "lumo", [item()])
        view = self.board.get(task_id, caller_tokens=1500)
        cost = self.record(task_id)["cost"]
        self.assertEqual(cost["caller_tokens"], 1500)
        self.assertEqual(cost["result_chars"], len(json.dumps(view, ensure_ascii=False)))
        self.assertGreater(cost["submit_chars"], 0)
        self.assertEqual(self.record(task_id)["judge_version"], adjudication.JUDGE_VERSION)


class CliTests(BoardTestCase):

    def run_cli(self, *argv):
        env = {"LLMORCH_RECORDS_DIR": str(self.tmp / "records"),
               "LLMORCH_PROJECTS_FILE": str(self.projects)}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_a_task_runs_end_to_end_through_the_cli(self):
        findings = self.tmp / "findings.json"
        findings.write_text(json.dumps([FINDING]), encoding="utf-8")
        answer = self.tmp / "items.json"
        answer.write_text(json.dumps([item()]), encoding="utf-8")
        code, sub = self.run_cli("submit", "--project", "demo", "--commit", self.head,
                                 "--findings", str(findings))
        self.assertEqual(code, 0)
        tid = sub["task_id"]
        self.assertEqual(self.run_cli("list", "--state", "open")[1]["tasks"][0]["task_id"], tid)
        self.assertEqual(self.run_cli("claim", tid, "--worker", "w")[0], 0)
        self.assertEqual(self.run_cli("submit-result", tid, str(answer), "--worker", "w")[0], 0)
        code, got = self.run_cli("get", tid, "--caller-tokens", "900")
        self.assertEqual((code, got["state"]), (0, "done"))

    def test_a_refusal_exits_1_with_its_reason(self):
        code, out = self.run_cli("get", "task_20260101_000000_abcdef")
        self.assertEqual(code, 1)
        self.assertIn("no task", out["error"])


class BoundaryTests(unittest.TestCase):

    def test_the_board_never_imports_mcp(self):
        code = "import sys, tasks.board, tasks.__main__; print(any(m == 'mcp' or m.startswith('mcp.') for m in sys.modules))"
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        self.assertEqual(out, "False")

    def test_file_sources_keep_lines_without_hunk_breaks(self):
        sources = adjudication.file_sources({"a.cpp": "int  x;\n\n  y();\n"})
        self.assertEqual(sources, {"a.cpp": ["int x;", "y();"]})


if __name__ == "__main__":
    unittest.main()
