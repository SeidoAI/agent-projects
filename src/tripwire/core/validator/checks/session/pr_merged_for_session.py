"""v0.13.2 — every worktree branch must have a merged PR before completed."""

from __future__ import annotations

from pathlib import Path

from tripwire.core import paths
from tripwire.core.gh_helpers import GhError, get_merged_pr_for_branch
from tripwire.core.validator._types import CheckResult, ValidationContext


def _pr_merged_for_branch(worktree_path: str, branch: str) -> bool:
    """Return True when ``branch`` has a merged PR on its origin.

    Mirrors ``session_complete._verify_pr_merged``: delegates to
    :func:`tripwire.core.gh_helpers.get_merged_pr_for_branch`, which
    runs ``gh pr list --state merged`` from inside the worktree so the
    right remote is picked up when sessions span multiple repos. Errors
    are conservative — treated as "not merged" so the operator re-runs
    once the env is healthy rather than getting a false green.
    """
    try:
        return get_merged_pr_for_branch(branch, cwd=worktree_path) is not None
    except GhError:
        return False


def check_pr_merged_for_session(ctx: ValidationContext) -> list[CheckResult]:
    """A session at `verified` must have a merged PR for every worktree
    branch before it can reach `completed`.

    Code: ``session/pr_not_merged``.

    v0.13.2: gate is exact ``== "verified"``, not ``at_or_past``.
    After completion, ``session complete`` removes the worktree dir
    without clearing ``runtime_state.worktrees``; re-validating a
    completed session would shell out into the missing cwd and
    surface a ``FileNotFoundError`` as a ``GhError`` (interpreted as
    "not merged"), producing permanent noise per completed session.
    The check is only meaningful at the verified → completed
    boundary; after that, completion itself was the proof.
    """
    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session = entity.model
        sid = session.id
        if str(session.status) != "verified":
            continue

        runtime = getattr(session, "runtime_state", None)
        worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []
        if not worktrees:
            results.append(
                CheckResult(
                    code="session/pr_not_merged",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/session.yaml",
                    field="runtime_state.worktrees",
                    message=(
                        f"Session {sid!r} has no recorded worktrees; cannot "
                        f"verify any PR merged."
                    ),
                    fix_hint=(
                        "Restore the session's worktree records, or run "
                        "`tripwire session abandon` if the session legitimately "
                        "cannot ship."
                    ),
                )
            )
            continue

        unmerged: list[str] = []
        for wt in worktrees:
            # Defensive: a worktree whose dir is gone (rare, but possible
            # if cleanup ran out of order) shouldn't surface as
            # "not merged" — it's an absent prerequisite, not a remote
            # state. Skip and let the next layer report it if needed.
            wt_path = Path(wt.worktree_path).expanduser()
            if not wt_path.is_dir():
                continue
            if not _pr_merged_for_branch(wt.worktree_path, wt.branch):
                unmerged.append(wt.branch)
        if unmerged:
            results.append(
                CheckResult(
                    code="session/pr_not_merged",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/session.yaml",
                    field="runtime_state.worktrees",
                    message=(
                        f"Session {sid!r}: no merged PR found for branch(es): "
                        f"{', '.join(unmerged)}"
                    ),
                    fix_hint=(
                        "Merge the PR(s) on GitHub, or run `tripwire session "
                        "abandon` if the session legitimately cannot ship."
                    ),
                )
            )
    return results
