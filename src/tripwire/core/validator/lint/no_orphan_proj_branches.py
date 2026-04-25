"""v0.7.9 §A9 — every local ``proj/<sid>`` branch needs a matching
session, AND the spawn-but-never-used pattern is forbidden.

Two failure modes covered:

1. **No matching session.yaml** — the branch references a session that
   doesn't exist. Likely a leftover from a deleted session.
2. **Empty branch + queued session** — the spawn created the branch
   but the agent never started, so the branch has zero commits ahead
   of the project's base ref. Surfaces today's
   ``proj/code-ci-cleanup`` / ``proj/v075-agent-loop`` /
   ``proj/v076-concept-drift-lint`` orphans.

Local branches only (``refs/heads/proj/``). The check runs in
``ctx.project_dir`` since that's where ``project.yaml`` and the
session-tracking branches live.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def local_proj_branches(repo_dir: Path) -> list[str]:
    """Return local branch names under ``refs/heads/proj/``.

    Degrades to ``[]`` on any failure (not a git repo, no proj/*
    branches, etc.). The validator must be local-first and silent on
    missing prerequisites.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/proj/",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def branch_is_empty(repo_dir: Path, branch: str, base: str) -> bool:
    """True if ``branch`` has zero commits ahead of ``base``.

    Returns ``False`` (assume non-empty, don't fire) on any git
    failure — local-first, no false positives when we can't tell.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "rev-list",
            f"{base}..{branch}",
            "--count",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    try:
        return int(result.stdout.strip() or "0") == 0
    except ValueError:
        return False


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    branches = local_proj_branches(ctx.project_dir)
    if not branches:
        return []

    sessions_by_id = {entity.model.id: entity.model for entity in ctx.sessions}
    base = (
        ctx.project_config.base_branch
        if ctx.project_config is not None
        else "main"
    )

    results: list[CheckResult] = []
    for branch in branches:
        sid = branch.removeprefix("proj/")
        session = sessions_by_id.get(sid)
        if session is None:
            results.append(
                CheckResult(
                    code="no_orphan_proj_branches/orphan",
                    severity="error",
                    message=(
                        f"Local branch {branch!r} has no matching session "
                        f"(no sessions/{sid}/session.yaml). The branch was "
                        f"likely created by a spawn whose agent never used it."
                    ),
                    fix_hint=(
                        f"Either restore the missing sessions/{sid}/ "
                        f"artifacts from history, OR delete the orphan "
                        f"branch with `git branch -D {branch}`."
                    ),
                )
            )
            continue

        if session.status == "queued" and branch_is_empty(
            ctx.project_dir, branch, base
        ):
            results.append(
                CheckResult(
                    code="no_orphan_proj_branches/empty_queued",
                    severity="error",
                    message=(
                        f"Local branch {branch!r} is empty (0 commits "
                        f"ahead of {base!r}) and its session is `queued`: "
                        f"the spawn created the branch but the agent never "
                        f"started."
                    ),
                    fix_hint=(
                        f"Either resume the session so the agent commits "
                        f"work, OR delete the branch with `git branch -D "
                        f"{branch}` and abandon the session."
                    ),
                )
            )

    return results
