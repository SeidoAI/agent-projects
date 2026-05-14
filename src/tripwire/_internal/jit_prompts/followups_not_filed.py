"""Followups-not-filed JIT prompt — KUI-139 / B5.

Fires on ``session.complete`` when a session's ``pm-response.yaml``
declares ``decision: deferred`` items with ``follow_up: KUI-XXX`` but
the referenced issues don't exist on disk. Enforces the standing
project rule "Follow-ups are immediate, not deferred" — a deferred
decision must be paired with an actually-filed issue, not a paper
promise.

Silently no-ops when the pm-response.yaml doesn't exist yet (the PM
hasn't responded), so the first session.complete invocation doesn't
spuriously fire.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import yaml

from tripwire._internal.jit_prompts import JitPrompt, JitPromptContext

_PM_RESPONSE_REL = Path("artifacts") / "pm-response.yaml"

_VARIATIONS: tuple[str, ...] = (
    """\
Your `pm-response.yaml` declared at least one `decision: deferred`
item with a `follow_up: <KEY>` reference, but that issue isn't on
disk. The project's standing rule is "Follow-ups are immediate, not
deferred" — a deferred decision must be paired with an actually-filed
issue, not a paper promise.

For each declared follow-up:

  1. Run `tripwire next-key` to get a fresh issue key (don't reuse
     the placeholder).
  2. Author `issues/<KEY>/issue.yaml` with the smallest reasonable
     scope you'd accept on the next session.
  3. Update the `pm-response.yaml` item's `follow_up:` to point at
     the real key if you allocated a new one.

Re-run with `--ack`. The marker requires fix-commit SHAs OR
`declared_no_findings: true`.
""",
    """\
Stop. The PM response defers items with `follow_up: KUI-XXX` but the
referenced issues aren't filed. Deferral without filing is the
shape of a TODO that never lands.

Walk every `decision: deferred` item in `pm-response.yaml`. For each
one whose `follow_up:` value doesn't resolve to a real
`issues/<KEY>/issue.yaml`:

  - File the issue now (or pick an existing key) with a real scope,
    not a placeholder body.
  - Re-run with `--ack` once the marker carries fix-commit SHAs OR
    `declared_no_findings: true` (the latter only after the
    pm-response is corrected to remove the spurious follow_up).
""",
    """\
Deferred items in `pm-response.yaml` are a contract: the work moves,
but it stays visible as a real issue with a real key. Right now,
that contract is broken — at least one `follow_up: <KEY>` reference
points at nothing.

Two ways forward:

  Path A — File the missing issues. For each unfiled `follow_up`,
  create the `issues/<KEY>/issue.yaml` with a scope you'd actually
  hand to a future session.
  Path B — Convert the deferral. If the deferral was wrong, change
  the `decision:` value in `pm-response.yaml` to `accepted` /
  `rejected` / `re-engaged` and remove the `follow_up:` field.

Either way, re-run with `--ack`. The marker is rejected if it lacks
fix-commit SHAs and does not declare `declared_no_findings: true`.
""",
)


class FollowupsNotFiledJitPrompt(JitPrompt):
    """Block when pm-response declares follow-ups that aren't on disk."""

    id: ClassVar[str] = "followups-not-filed"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    def fire(self, ctx: JitPromptContext) -> str:
        idx = ctx.variation_index(len(_VARIATIONS))
        return _VARIATIONS[idx]

    def is_acknowledged(self, ctx: JitPromptContext) -> bool:
        marker = ctx.ack_path(self.id)
        if not marker.is_file():
            return False
        return _marker_substantive(marker)

    def should_fire(self, ctx: JitPromptContext) -> bool:
        return bool(_missing_followups(ctx.project_dir, ctx.session_id))


def _missing_followups(project_dir: Path, session_id: str) -> set[str]:
    """Return the set of follow-up issue keys declared but not filed.

    Reads ``sessions/<sid>/artifacts/pm-response.yaml`` and walks
    items[]; any ``decision: deferred`` entry with ``follow_up: KEY``
    is checked against ``issues/<KEY>/issue.yaml``. Missing files are
    collected and returned.
    """
    from tripwire.core import paths

    pm_path = paths.session_dir(project_dir, session_id) / _PM_RESPONSE_REL
    if not pm_path.is_file():
        return set()

    try:
        payload = yaml.safe_load(pm_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(payload, dict):
        return set()

    items = payload.get("items")
    if not isinstance(items, list):
        return set()

    missing: set[str] = set()
    issues_root = paths.issues_dir(project_dir)
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("decision") != "deferred":
            continue
        follow_up = item.get("follow_up")
        if not isinstance(follow_up, str) or not follow_up.strip():
            continue
        key = follow_up.strip()
        issue_yaml = issues_root / key / "issue.yaml"
        if not issue_yaml.is_file():
            missing.add(key)
    return missing


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


__all__ = ["FollowupsNotFiledJitPrompt"]
