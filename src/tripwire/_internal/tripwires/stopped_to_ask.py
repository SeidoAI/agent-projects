"""Stopped-to-ask tripwire — KUI-140 / B6.

Fires on ``session.complete`` when:

  1. The session plan declares a ``## Stop and ask`` section,
  2. Committed work in the session touched files outside the
     ``key_files`` declared in ``session.yaml``, and
  3. No agent comment under ``sessions/<sid>/comments/`` invoked the
     stop-and-ask path.

The signal is "scope creep that didn't surface a stop-and-ask
comment" — the session drifted into territory the plan said should
trigger an explicit pause, but the agent kept going.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

import yaml

from tripwire._internal.tripwires import Tripwire, TripwireContext

_STOP_AND_ASK_HEADER_RE = re.compile(
    r"^\s*##\s*stop\s*and\s*ask\b", re.IGNORECASE | re.MULTILINE
)

_STOP_ASK_KEYWORDS = (
    "stop_and_ask",
    "stop and ask",
    "stop-and-ask",
    "blocked on",
    "please decide",
)


_VARIATIONS: tuple[str, ...] = (
    """\
Your session plan declared a `## Stop and ask` section, and the
session's commits touched files outside the `key_files` you scoped
in `session.yaml`. There's no comment under
`sessions/<sid>/comments/` invoking the stop-and-ask path. The work
drifted across a boundary the plan said should trigger an explicit
pause.

Do one of these now:

  1. File a stop-and-ask comment retroactively, name the call you
     made, and either get explicit PM sign-off OR re-scope the
     committed work.
  2. Update `session.yaml.key_files` to include the drifted-into
     files and document the scope expansion in `decisions.md`.
  3. Roll back the out-of-scope commits.

Re-run with `--ack`. The marker requires fix-commit SHAs OR
`declared_no_findings: true`.
""",
    """\
Stop. The plan said "stop and ask" applied here, you didn't, and
the diff confirms it: at least one committed file lives outside the
session's declared `key_files`. Silent scope creep is the failure
mode this tripwire catches.

Walk the commits in this session. For each file that's outside
`key_files`:

  - Was the change actually in scope (and `key_files` was wrong)?
    Update `session.yaml.key_files` and document in
    `decisions.md`.
  - Was it real scope creep? File a stop-and-ask comment that
    surfaces the call, even after the fact, and either revert the
    out-of-scope work or get explicit PM sign-off.

Re-run with `--ack` after the marker is substantive.
""",
    """\
The contract `## Stop and ask` declares is: "if the work crosses
this boundary, surface a comment and pause." The boundary in your
session is `key_files`. Right now, the diff has crossed it, and
no stop-and-ask comment exists.

Two recovery paths, pick one:

  Path A — Re-scope. The work that crossed the boundary belongs in
  this session. Update `session.yaml.key_files` to reflect reality
  and explain the expansion in `decisions.md`.
  Path B — Surface the call. File a comment under
  `sessions/<sid>/comments/` with `kind: stop_and_ask` and a body
  describing the boundary you crossed and why. Roll back if the
  call should have been "no, don't do this".

Re-run with `--ack` once the marker carries fix-commit SHAs OR
`declared_no_findings: true`.
""",
)


class StoppedToAskTripwire(Tripwire):
    """Block when a stop-and-ask plan section is bypassed silently."""

    id: ClassVar[str] = "stopped-to-ask"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    def fire(self, ctx: TripwireContext) -> str:
        idx = ctx.variation_index(len(_VARIATIONS))
        return _VARIATIONS[idx]

    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        marker = ctx.ack_path(self.id)
        if not marker.is_file():
            return False
        return _marker_substantive(marker)

    def should_fire(self, ctx: TripwireContext) -> bool:
        plan_path = (
            ctx.project_dir / "sessions" / ctx.session_id / "artifacts" / "plan.md"
        )
        if not plan_path.is_file():
            return False
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
        except OSError:
            return False
        if not _plan_has_stop_and_ask(plan_text):
            return False
        if _stop_ask_signalled(ctx.project_dir, ctx.session_id):
            return False
        key_files = _session_key_files(ctx.project_dir, ctx.session_id)
        touched = _session_touched_files(ctx.project_dir, ctx.session_id)
        return _scope_creep(touched, key_files)


def _plan_has_stop_and_ask(plan_text: str) -> bool:
    if not plan_text:
        return False
    return bool(_STOP_AND_ASK_HEADER_RE.search(plan_text))


def _stop_ask_signalled(project_dir: Path, session_id: str) -> bool:
    """Return True iff any session comment carries the stop-ask signal.

    A comment counts if its ``kind`` is ``stop_and_ask`` OR its body
    contains one of the well-known phrases. Unreadable / malformed
    files are ignored.
    """
    comments_dir = project_dir / "sessions" / session_id / "comments"
    if not comments_dir.is_dir():
        return False
    for path in comments_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        kind = (data.get("kind") or "").strip().lower()
        if kind == "stop_and_ask":
            return True
        body = data.get("body")
        if isinstance(body, str):
            lower = body.lower()
            if any(kw in lower for kw in _STOP_ASK_KEYWORDS):
                return True
    return False


def _scope_creep(touched: Iterable[str], key_files: list[str]) -> bool:
    """Return True iff at least one touched file is outside key_files.

    A touched file is "inside" if it equals a key entry or starts
    with a key entry that ends in ``/`` (directory prefix). With no
    key_files, anything touched counts as creep — the session
    declared no scope.
    """
    touched_list = list(touched)
    if not touched_list:
        return False
    if not key_files:
        return True
    for f in touched_list:
        if not _file_in_key_set(f, key_files):
            return True
    return False


def _file_in_key_set(path: str, key_files: list[str]) -> bool:
    for key in key_files:
        if not key:
            continue
        if key.endswith("/"):
            if path.startswith(key):
                return True
        elif path == key:
            return True
    return False


def _session_key_files(project_dir: Path, session_id: str) -> list[str]:
    syaml = project_dir / "sessions" / session_id / "session.yaml"
    if not syaml.is_file():
        return []
    try:
        text = syaml.read_text(encoding="utf-8")
    except OSError:
        return []
    # Strip frontmatter delimiters if present.
    payload_text = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            payload_text = parts[1]
    try:
        data = yaml.safe_load(payload_text) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("key_files") or []
    return [str(x) for x in raw if isinstance(x, str)]


def _session_touched_files(project_dir: Path, session_id: str) -> list[str]:
    """Return the union of files touched by HEAD relative to base_branch.

    Reads ``project.yaml.base_branch`` (canonical source) and runs
    ``git diff --name-only <base>...HEAD``. Falls back to ``main`` if
    project.yaml is missing or unreadable. Best-effort: missing git
    or unreachable refs return ``[]``. Monkeypatched in unit tests.
    """
    base_branch = _resolve_base_branch(project_dir)
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
            cwd=project_dir,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _resolve_base_branch(project_dir: Path) -> str:
    """Read ``project.yaml.base_branch`` or fall back to ``main``.

    Codex P1 #1 on PR #79: hardcoding ``main`` silently breaks
    scope-creep detection for repos using ``develop`` /
    ``master`` / etc. Reading project.yaml directly avoids importing
    the typed loader (which forbids extra fields and would reject
    minimal test fixtures).
    """
    pyaml = project_dir / "project.yaml"
    if not pyaml.is_file():
        return "main"
    try:
        data = yaml.safe_load(pyaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return "main"
    if not isinstance(data, dict):
        return "main"
    base = data.get("base_branch")
    if isinstance(base, str) and base.strip():
        return base.strip()
    return "main"


def _marker_substantive(marker_path: Path) -> bool:
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    commits = data.get("fix_commits")
    declared = data.get("declared_no_findings")
    has_commits = isinstance(commits, list) and any(
        isinstance(s, str) and s.strip() for s in commits
    )
    return bool(has_commits or declared is True)


__all__ = ["StoppedToAskTripwire"]
