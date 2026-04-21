"""Session readiness checks, shared by queue, spawn, and session check.

Extracted from ``tripwire.cli.session._compute_readiness`` so that all three
commands share one source of truth.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tripwire.core.handoff_store import handoff_exists, load_handoff
from tripwire.core.session_store import load_session
from tripwire.core.store import load_issue


@dataclass
class ReadinessItem:
    label: str
    passing: bool
    severity: str  # "error" | "warning"
    fix_hint: str | None = None


@dataclass
class ReadinessReport:
    ready: bool
    items: list[ReadinessItem] = field(default_factory=list)


def check_readiness(
    project_dir: Path,
    session_id: str,
    *,
    kind: Literal["queue", "spawn", "check"] = "check",
) -> ReadinessReport:
    """Compute readiness for a session.

    Raises FileNotFoundError if the session doesn't exist.
    """
    session = load_session(project_dir, session_id)
    items: list[ReadinessItem] = []

    # 1. Required planning artifacts (per manifest).
    from tripwire.core.manifest_loader import load_artifact_manifest

    manifest, _ = load_artifact_manifest(project_dir)
    if manifest is not None:
        sess_dir = project_dir / "sessions" / session_id
        for entry in manifest.artifacts:
            if entry.produced_at != "planning" or entry.owned_by != "pm":
                continue
            if not entry.required:
                continue
            present = (sess_dir / entry.file).is_file()
            items.append(
                ReadinessItem(
                    label=f"planning artifact: {entry.file}",
                    passing=present,
                    severity="error",
                    fix_hint=(
                        None if present else f"Write {entry.file} from {entry.template}"
                    ),
                )
            )

    # 2. Blockers on issues.
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            items.append(
                ReadinessItem(
                    label=f"issue {issue_key} referenced by session not found",
                    passing=False,
                    severity="error",
                )
            )
            continue
        for blocker_key in issue.blocked_by or []:
            try:
                blocker = load_issue(project_dir, blocker_key)
            except FileNotFoundError:
                items.append(
                    ReadinessItem(
                        label=f"blocker {blocker_key} referenced by {issue_key} not found",
                        passing=False,
                        severity="error",
                    )
                )
                continue
            if blocker.status != "done":
                items.append(
                    ReadinessItem(
                        label=f"blocker: {blocker_key} ({blocker.status})",
                        passing=False,
                        severity="error",
                        fix_hint=f"Wait for {blocker_key} to reach status=done",
                    )
                )

    # 3. Blocked-by-sessions check (v0.6c addition — not in v0.6a's
    #    _compute_readiness which only checked issue blockers).
    for dep_id in session.blocked_by_sessions:
        try:
            dep = load_session(project_dir, dep_id)
        except FileNotFoundError:
            items.append(
                ReadinessItem(
                    label=f"blocked_by_sessions: {dep_id} not found",
                    passing=False,
                    severity="warning",
                    fix_hint=f"Session {dep_id} does not exist",
                )
            )
            continue
        if dep.status != "completed":
            items.append(
                ReadinessItem(
                    label=f"blocked_by_sessions: {dep_id} ({dep.status})",
                    passing=False,
                    severity="error",
                    fix_hint=f"Wait for session {dep_id} to complete",
                )
            )

    # 4. Handoff.yaml presence + validity.
    if not handoff_exists(project_dir, session_id):
        items.append(
            ReadinessItem(
                label="handoff.yaml present",
                passing=False,
                severity="error",
                fix_hint="Run /pm-session-queue to create handoff.yaml",
            )
        )
    else:
        try:
            load_handoff(project_dir, session_id)
            items.append(
                ReadinessItem(
                    label="handoff.yaml valid + branch per convention",
                    passing=True,
                    severity="error",
                )
            )
        except Exception as exc:
            items.append(
                ReadinessItem(
                    label=f"handoff.yaml invalid: {exc}",
                    passing=False,
                    severity="error",
                    fix_hint="Fix handoff.yaml to match schema",
                )
            )

    # 5. Spawn-specific checks.
    if kind == "spawn":
        # Check claude CLI on PATH.
        if not shutil.which("claude"):
            items.append(
                ReadinessItem(
                    label="claude CLI on PATH",
                    passing=False,
                    severity="error",
                    fix_hint="Install Claude Code or add to PATH",
                )
            )

    errors = [i for i in items if not i.passing and i.severity == "error"]
    return ReadinessReport(ready=len(errors) == 0, items=items)
