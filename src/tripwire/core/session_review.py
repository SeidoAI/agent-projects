"""Session review: check a session's PR diff against the session's issues.

Pure functions (no git or PR I/O) — the CLI wrapper gathers PR files via
`gh pr view` and calls these to produce a `ReviewReport`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class IssueReview:
    key: str
    criteria: list[str]
    criteria_met: list[bool]
    criteria_evidence: list[str | None]


@dataclass
class Deviations:
    unspec_files: list[str] = field(default_factory=list)
    extra_deps: list[str] = field(default_factory=list)
    layout_divergence: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    session_id: str
    pr_number: int | None
    issue_reviews: list[IssueReview] = field(default_factory=list)
    deviations: Deviations = field(default_factory=Deviations)
    plan_adherence_ok: bool = True
    plan_unmatched_steps: list[str] = field(default_factory=list)
    stop_and_ask_clauses: list[str] = field(default_factory=list)
    verdict: str = "approved"  # approved | approved_with_notes | rejected

    @property
    def exit_code(self) -> int:
        if self.verdict == "rejected":
            return 2
        if self.verdict == "approved_with_notes":
            return 1
        return 0


def parse_acceptance_criteria(body: str) -> list[str]:
    """Extract checkbox bullets under `## Acceptance criteria`."""
    pattern = re.compile(
        r"##\s+Acceptance criteria\s*\n(.*?)(?:\n##\s|$)", re.S
    )
    m = pattern.search(body)
    if not m:
        return []
    items: list[str] = []
    for raw_line in m.group(1).splitlines():
        line = raw_line.strip()
        if (
            line.startswith("- [ ]")
            or line.startswith("- [x]")
            or line.startswith("- [X]")
        ):
            items.append(line[5:].strip())
    return items


def parse_repo_scope(body: str) -> list[str]:
    """Extract bullets under `## Repo scope`."""
    pattern = re.compile(r"##\s+Repo scope\s*\n(.*?)(?:\n##\s|$)", re.S)
    m = pattern.search(body)
    if not m:
        return []
    items: list[str] = []
    for raw_line in m.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def detect_deviations(pr_files: list[str], scope_paths: list[str]) -> dict:
    """Return files in the PR that fall outside any declared scope path."""
    normalized = [p.rstrip("/") + "/" for p in scope_paths]
    unspec: list[str] = []
    for f in pr_files:
        if not any(f.startswith(sp) for sp in normalized):
            unspec.append(f)
    return {"unspec_files": unspec}


def check_plan_adherence(
    plan_md: str, pr_files: list[str]
) -> tuple[bool, list[str]]:
    """Return (ok, list of paths named in the plan that aren't in pr_files)."""
    paths_in_plan = re.findall(
        r"`([a-zA-Z0-9_./\-]+\.(?:py|ts|tsx|js|md|yaml|yml))`", plan_md
    )
    unmatched: list[str] = []
    for p in set(paths_in_plan):
        if p not in pr_files:
            unmatched.append(p)
    return (len(unmatched) == 0, sorted(unmatched))


def check_stop_and_ask(issue_body: str) -> list[str]:
    """Return any line containing a 'stop and ask' clause from the issue body."""
    pattern = re.compile(r"^(.*stop.{0,3}and.{0,3}ask.*)$", re.M | re.I)
    return [m.strip() for m in pattern.findall(issue_body)]
