"""The projects a task can name, from a local projects.json (git-ignored;
projects.example.json shows the shape), and what a task reads from them:
the checkout at a commit, the rule files whose paths match, the files read
from the working tree, and the denylist.

Reads files and runs git (argument lists, no shell); no network.
"""

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SHA = re.compile(r"[0-9a-f]{7,40}")


class ProjectError(ValueError):
    """A project, commit or path a task cannot use; the message says why."""


def projects_path() -> Path:
    return Path(os.environ.get("LLMORCH_PROJECTS_FILE") or REPO_ROOT / "projects.json")


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    rules: Optional[Path] = None
    always: Tuple[str, ...] = ()
    denylist: Optional[Path] = None
    never: Tuple[str, ...] = ()
    _rule_globs: Dict[str, List[str]] = field(default_factory=dict, compare=False)

    def git(self, *args: str, cwd: Optional[Path] = None) -> str:
        try:
            # --no-optional-locks: status never rewrites the index of a tree others build in
            out = subprocess.run(["git", "--no-optional-locks", "-C", str(cwd or self.root), *args],
                                 capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", b"") or b""
            raise ProjectError(f"git {' '.join(args[:2])} failed: "
                               f"{detail.decode('utf-8', 'replace').strip() or exc}") from None
        return out.stdout.decode("utf-8", "replace")

    def resolve(self, commit: str) -> str:
        if not SHA.fullmatch(commit or ""):
            raise ProjectError(f"not a commit id: {commit!r}")
        return self.git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}").strip()

    def checkout(self, commit: str) -> Path:
        """The worktree (or the main clone) whose HEAD is the commit."""
        for block in self.git("worktree", "list", "--porcelain").split("\n\n"):
            fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
            if fields.get("HEAD") == commit and "worktree" in fields:
                return Path(fields["worktree"])
        raise ProjectError(f"no checkout of {self.name} is at {commit[:12]}: "
                           "check out the work branch's commit in a worktree first")

    def tracked(self, commit: str, path: str) -> bool:
        try:
            self.git("cat-file", "-e", f"{commit}:{path}")
            return True
        except ProjectError:
            return False

    def show(self, commit: str, path: str) -> str:
        return self.git("show", f"{commit}:{path}")

    def dirty(self, checkout: Path, paths: List[str]) -> List[str]:
        if not paths:
            return []
        out = self.git("status", "--porcelain", "--", *paths, cwd=checkout)
        return [line[3:] for line in out.splitlines() if line.strip()]

    def check_path(self, path: str) -> str:
        """A task path, relative and inside the project, never a listed one."""
        p = path.replace("\\", "/").strip()
        while p.startswith("./"):
            p = p[2:]
        if not p or p.startswith("/") or re.match(r"[A-Za-z]:", p) or ".." in p.split("/"):
            raise ProjectError(f"not a path inside the project: {path!r}")
        if any(p == n.rstrip("/") or p.startswith(n.rstrip("/") + "/") for n in self.never):
            raise ProjectError(f"{p} is under a path tasks never list")
        return p

    def rule_globs(self) -> Dict[str, List[str]]:
        """Each rule file's paths: globs, read from the working tree."""
        if self._rule_globs or self.rules is None:
            return self._rule_globs
        folder = self.root / self.rules
        for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            self._rule_globs[f"{self.rules.as_posix()}/{f.name}"] = _frontmatter_paths(
                f.read_text(encoding="utf-8"))
        return self._rule_globs

    def matching_rules(self, paths: List[str]) -> List[str]:
        return [rule for rule, globs in self.rule_globs().items()
                if any(_glob(g).fullmatch(p) for g in globs for p in paths)]

    def read_working(self, path: str) -> Tuple[str, str]:
        """A working-tree file of the main clone, and its SHA-256."""
        data = (self.root / path).read_bytes()
        return data.decode("utf-8", "replace"), hashlib.sha256(data).hexdigest()

    def deny_patterns(self) -> List[re.Pattern]:
        """One regex per line, case-insensitive; '#' comments and 'allow'
        lines skipped. A configured list that is missing refuses every task."""
        if self.denylist is None:
            return []
        path = self.root / self.denylist
        if not path.is_file():
            raise ProjectError(f"{self.name}'s denylist is missing; no task leaves without it")
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("allow "):
                out.append(re.compile(line, re.IGNORECASE))
        return out


def _frontmatter_paths(text: str) -> List[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    globs, inside = [], False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if re.match(r"paths\s*:", line):
            inside = True
            continue
        item = re.match(r"\s*-\s*(.+)", line)
        if inside and item:
            globs.append(item.group(1).strip().strip("'\""))
        elif line and not line[0].isspace():
            inside = False
    return globs


def _glob(pattern: str) -> re.Pattern:
    """A rules glob: '**' any depth, '*' and '?' within one path part."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def load_project(name: str, path: Optional[Path] = None) -> Project:
    path = Path(path or projects_path())
    if not path.is_file():
        raise ProjectError(f"no {path.name}: copy projects.example.json and name your projects")
    entry = json.loads(path.read_text(encoding="utf-8")).get("projects", {}).get(name)
    if not isinstance(entry, dict) or "root" not in entry:
        raise ProjectError(f"no project {name!r} in {path.name}")
    root = Path(entry["root"])
    root = root if root.is_absolute() else (path.parent / root)
    rules, deny = entry.get("rules"), entry.get("denylist")
    return Project(name=name, root=root.resolve(), rules=Path(rules) if rules else None,
                   always=tuple(entry.get("always", [])),
                   denylist=Path(deny) if deny else None, never=tuple(entry.get("never", [])))
