"""Side-effect registry for the v0.13 workflow executor.

Each registered side-effect is referenced from ``workflow.yaml`` by id
in a route's ``side_effects:`` array. The executor (WS3) looks up the
id in this registry and invokes ``apply(ctx)`` in declared order.

The contract:

- ``apply(ctx)`` runs the side effect. Raises :class:`SideEffectFailure`
  if it cannot succeed and the transition should be rolled back.
- ``inverse(ctx, result)`` undoes a successful ``apply``. Called by the
  executor when a later side-effect or rollback fires. Side effects
  declared ``idempotent=True`` skip their inverse during rollback —
  used for best-effort handlers like ``flip_drafts_to_*`` whose
  network-bound effects are unsafe (or impossible) to rewind.
- ``idempotent`` indicates the side effect is "fire-and-forget" — the
  executor will not invoke its inverse during rollback. Best-effort or
  read-only handlers (gates that raise on fail; ``gh`` calls that
  flip state but cannot be cleanly un-flipped) carry this.

WS2 wires the registry. WS3 plumbs the executor against it. WS4
re-routes existing callers through the executor so each side-effect
fires from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tripwire.core.workflow.schema import WorkflowRoute
from tripwire.models.session import AgentSession


class SideEffectFailure(RuntimeError):
    """Raised by a side-effect's ``apply`` when the transition must abort.

    The executor catches this and runs inverses of previously-applied
    side-effects (rollback). The string passed in becomes the
    ``transition.rejected`` event reason.
    """


@dataclass(frozen=True)
class SideEffectContext:
    """Inputs handed to every side-effect's ``apply``/``inverse``."""

    project_dir: Path
    session: AgentSession
    route: WorkflowRoute
    flags: dict[str, Any]
    project_id: str | None = None


@dataclass
class SideEffectResult:
    """Return value from a side-effect's ``apply``.

    ``data`` carries arbitrary state that ``inverse`` may need to undo
    the operation (e.g. the set of issues a sweep touched, with
    pre-snapshot statuses). The executor passes the same instance to
    ``inverse`` if the rollback fires.
    """

    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SideEffect:
    """One registered side-effect handler."""

    id: str
    apply: Callable[[SideEffectContext], SideEffectResult]
    inverse: Callable[[SideEffectContext, SideEffectResult], None] | None = None
    idempotent: bool = False


_REGISTRY: dict[str, SideEffect] = {}


def register(effect: SideEffect) -> None:
    """Add ``effect`` to the registry. Last write wins, but registering
    the same id twice from different modules is almost always a bug —
    callers should keep registrations colocated with their definitions.
    """
    _REGISTRY[effect.id] = effect


def get(effect_id: str) -> SideEffect | None:
    """Return the registered handler for ``effect_id``, or ``None``."""
    return _REGISTRY.get(effect_id)


def known_ids() -> set[str]:
    """Set of all registered side-effect ids. Plumbed into
    :func:`tripwire.core.workflow.schema.validate_workflow_spec` as
    ``known_side_effects=`` so the loader can lint stale references.
    """
    return set(_REGISTRY)


def clear() -> None:
    """Test-only: empty the registry. Production code never calls this."""
    _REGISTRY.clear()


# ----------------------------------------------------------------------
# Built-in side effects
# ----------------------------------------------------------------------
#
# These wrap existing implementations in the codebase. WS2 is mostly
# id-tagging and signature-normalising; the deep logic already lives in
# session_complete.py, session_abandon.py, session_reopen.py,
# git_helpers.py, and status_contract.py. WS3 adds inverses for the
# non-idempotent handlers when the executor's rollback path is wired.


def _sweep_issues_forward_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Advance member issues to match the route's target status.

    Reads ``ctx.route.to_ref`` (not ``ctx.session.status``) so the sweep
    fires correctly whether it runs before or after the status flip.
    Forward-only: an issue already past the target stays put; off-path
    issues (deferred, abandoned) are left alone. Pre-state captured into
    ``result.data["pre_state"]`` for rollback.
    """
    from tripwire.core.status_contract import sweep_issues
    from tripwire.core.store import load_issue

    pre_state: dict[str, str] = {}
    for issue_key in ctx.session.issues:
        try:
            issue = load_issue(ctx.project_dir, issue_key)
        except FileNotFoundError:
            continue
        pre_state[issue_key] = issue.status
    target = ctx.route.to_ref
    swept = sweep_issues(ctx.project_dir, ctx.session, target) or []
    return SideEffectResult(data={"swept": list(swept), "pre_state": pre_state})


def _sweep_issues_forward_inverse(
    ctx: SideEffectContext, result: SideEffectResult
) -> None:
    """Restore each swept issue's status from the pre-apply snapshot."""
    from tripwire.core.store import load_issue, save_issue

    pre_state: dict[str, str] = result.data.get("pre_state", {})
    for issue_key in result.data.get("swept", []):
        if issue_key not in pre_state:
            continue
        try:
            issue = load_issue(ctx.project_dir, issue_key)
        except FileNotFoundError:
            continue
        issue.status = pre_state[issue_key]
        save_issue(ctx.project_dir, issue)


def _rebase_pt_branch_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Rebase the session's PT (project-tracking) worktree onto origin/main.

    Skipped if the session has no PT worktree (no entry whose branch
    starts with ``proj/``). Raises :class:`SideEffectFailure` on a
    rebase conflict — the executor surfaces a structured rejection.
    """
    from tripwire.core.git_helpers import (
        RebaseConflict,
        fetch_origin,
        rebase_branch_onto,
    )

    if ctx.session.runtime_state is None:
        return SideEffectResult()
    pt = next(
        (
            w
            for w in ctx.session.runtime_state.worktrees
            if w.branch.startswith("proj/")
        ),
        None,
    )
    if pt is None:
        return SideEffectResult()
    wt_path = Path(pt.worktree_path)
    # Mirror the v0.12 `_maybe_rebase_pt_branch` guard: if the PT worktree
    # was cleaned up by `complete` and not yet recreated by `spawn --resume`,
    # the path is gone. Skip the rebase rather than hard-fail the transition.
    if not wt_path.is_dir():
        return SideEffectResult()
    try:
        fetch_origin(wt_path)
        rebase_branch_onto(wt_path, "origin/main")
    except RebaseConflict as exc:
        raise SideEffectFailure(f"pt_rebase_conflict: {exc}") from exc
    return SideEffectResult(data={"branch": pt.branch})


def _flip_drafts_to_ready_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Mark every draft PR on the session's worktrees as ready-for-review."""
    from tripwire.core.session_complete import _flip_drafts_to_ready

    _flip_drafts_to_ready(ctx.session)
    return SideEffectResult()


def _flip_drafts_to_draft_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Flip ready PRs back to draft (used by reopen). Best-effort."""
    import subprocess

    if ctx.session.runtime_state is None:
        return SideEffectResult()
    flipped: list[str] = []
    for wt in ctx.session.runtime_state.worktrees:
        if not wt.draft_pr_url:
            continue
        try:
            subprocess.run(
                ["gh", "pr", "ready", wt.draft_pr_url, "--undo"],
                check=False,
                capture_output=True,
                text=True,
            )
            flipped.append(wt.draft_pr_url)
        except OSError:
            continue
    return SideEffectResult(data={"flipped": flipped})


def _verify_prs_merged_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Gate: every worktree's branch must have a merged PR. Raises on fail."""
    from tripwire.core.session_complete import CompleteError, _verify_pr_merged

    try:
        _verify_pr_merged(ctx.session)
    except CompleteError as exc:
        raise SideEffectFailure(f"prs_not_merged: {exc}") from exc
    return SideEffectResult()


def _verify_review_ok_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Gate: most-recent review.json exit_code ≤ 1. Raises on fail."""
    from tripwire.core.session_complete import CompleteError, _verify_review_ok

    try:
        _verify_review_ok(ctx.project_dir, ctx.session)
    except CompleteError as exc:
        raise SideEffectFailure(f"review_not_ok: {exc}") from exc
    return SideEffectResult()


def _verify_issue_artifacts_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Gate: every required issue artifact exists at the issue's status."""
    from tripwire.core.session_complete import CompleteError, _verify_issue_artifacts

    try:
        _verify_issue_artifacts(ctx.project_dir, ctx.session)
    except CompleteError as exc:
        raise SideEffectFailure(f"missing_artifacts: {exc}") from exc
    return SideEffectResult()


def _kill_runtime_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Best-effort: terminate the session's running runtime handle."""
    if ctx.session.runtime_state is None:
        return SideEffectResult()
    pid = ctx.session.runtime_state.pid
    if pid is None:
        return SideEffectResult()
    import os
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    return SideEffectResult(data={"pid": pid})


def _close_open_prs_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Best-effort: close any PR the session has open across its worktrees."""
    from tripwire.core.session_abandon import _close_pr_for_branch

    if ctx.session.runtime_state is None:
        return SideEffectResult()
    closed: list[int] = []
    for wt in ctx.session.runtime_state.worktrees:
        if not wt.branch:
            continue
        verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
        if verdict.closed_pr is not None and verdict.closed_pr > 0:
            closed.append(verdict.closed_pr)
    return SideEffectResult(data={"closed_prs": closed})


def _remove_worktrees_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Best-effort: remove every recorded worktree directory."""
    from tripwire.core.git_helpers import worktree_remove

    if ctx.session.runtime_state is None:
        return SideEffectResult()
    removed: list[str] = []
    for wt in ctx.session.runtime_state.worktrees:
        try:
            worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
            removed.append(wt.worktree_path)
        except Exception:
            continue
    return SideEffectResult(data={"removed": removed})


def _append_pm_followup_stub_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Append the PM follow-up section to plan.md if absent (used by reopen)."""
    plan_path = ctx.project_dir / "sessions" / ctx.session.id / "plan.md"
    if not plan_path.is_file():
        return SideEffectResult()
    text = plan_path.read_text(encoding="utf-8")
    if "## PM follow-up" in text:
        return SideEffectResult()
    reason = ctx.flags.get("reason", "<reason omitted>")
    appended = (
        f"\n\n## PM follow-up\n\n"
        f"Session reopened by PM. Reason: {reason}.\n\n"
        f"Re-engage the agent via `tripwire session spawn {ctx.session.id} --resume`.\n"
    )
    plan_path.write_text(text + appended, encoding="utf-8")
    return SideEffectResult(data={"plan_path": str(plan_path)})


def _reset_acks_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Optionally reset session ack markers — fires only if flag set."""
    if not ctx.flags.get("reset_acks", False):
        return SideEffectResult()
    from tripwire.core.session_reopen import _reset_session_acks

    reason = ctx.flags.get("reason", "session reopened")
    n = _reset_session_acks(ctx.project_dir, ctx.session.id, reason)
    return SideEffectResult(data={"acks_deleted": n})


def _append_audit_log_entry_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Append a JSON line to ``.tripwire/audit.jsonl``.

    The action defaults to ``transition`` but ``ctx.flags["action"]`` can
    override (e.g. ``session_reopen`` writes ``action: session_reopen``).

    ``to_status`` reads from ``ctx.route.to_ref`` (the target declared by
    the route) — NOT from ``ctx.session.status`` which still holds the
    source status when this side-effect fires (side-effects run BEFORE
    the status flip, see ``transitions._run_gate``).
    """
    from datetime import datetime, timezone

    from tripwire.core.session_reopen import _audit_path
    from tripwire.ui.services._atomic_write import append_jsonl

    audit = _audit_path(ctx.project_dir)
    audit.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(
        audit,
        {
            "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": ctx.flags.get("action", "transition"),
            "session_id": ctx.session.id,
            "route_id": ctx.route.id,
            "from_status": ctx.flags.get("from_status"),
            "to_status": ctx.route.to_ref,
            "reason": ctx.flags.get("reason"),
        },
    )
    return SideEffectResult()


def _append_telemetry_row_apply(ctx: SideEffectContext) -> SideEffectResult:
    """Append a routing-telemetry row for analytics. Best-effort.

    Mirrors the legacy ``session_complete`` path: compute cost from the
    session's log, then build and append the row.
    ``build_telemetry_row`` requires a numeric ``cost_usd``; the
    historical ``cost_usd=None`` shortcut would raise ``TypeError`` and
    the broad ``except`` would silently swallow it — meaning no row was
    ever written for executor-driven completions.
    """
    try:
        from tripwire.core.routing_telemetry import (
            append_telemetry_row,
            build_telemetry_row,
        )
        from tripwire.core.session_cost import compute_session_cost

        cost = compute_session_cost(ctx.project_dir, ctx.session.id).total_usd
        row = build_telemetry_row(ctx.project_dir, ctx.session, cost_usd=cost)
        append_telemetry_row(ctx.project_dir, row)
    except Exception:
        # Telemetry must never block a transition.
        pass
    return SideEffectResult()


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


def _register_builtins() -> None:
    register(
        SideEffect(
            id="sweep_issues_forward",
            apply=_sweep_issues_forward_apply,
            inverse=_sweep_issues_forward_inverse,
            idempotent=False,
        )
    )
    register(
        SideEffect(
            id="rebase_pt_branch",
            apply=_rebase_pt_branch_apply,
            inverse=None,  # rebase un-rebase is fragile; lean on git's --abort
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="flip_drafts_to_ready",
            apply=_flip_drafts_to_ready_apply,
            inverse=None,  # gh-bound; cannot reliably un-flip
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="flip_drafts_to_draft",
            apply=_flip_drafts_to_draft_apply,
            inverse=None,  # gh-bound; cannot reliably un-flip
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="verify_prs_merged",
            apply=_verify_prs_merged_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="verify_review_ok",
            apply=_verify_review_ok_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="verify_issue_artifacts",
            apply=_verify_issue_artifacts_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="kill_runtime",
            apply=_kill_runtime_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="close_open_prs",
            apply=_close_open_prs_apply,
            inverse=None,  # closed PRs cannot be cleanly reopened
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="remove_worktrees",
            apply=_remove_worktrees_apply,
            inverse=None,  # filesystem deletion; not invertible
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="append_pm_followup_stub",
            apply=_append_pm_followup_stub_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="reset_acks",
            apply=_reset_acks_apply,
            inverse=None,  # ack markers cannot be re-created from outside
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="append_audit_log_entry",
            apply=_append_audit_log_entry_apply,
            inverse=None,
            idempotent=True,
        )
    )
    register(
        SideEffect(
            id="append_telemetry_row",
            apply=_append_telemetry_row_apply,
            inverse=None,
            idempotent=True,
        )
    )


_register_builtins()


__all__ = [
    "SideEffect",
    "SideEffectContext",
    "SideEffectFailure",
    "SideEffectResult",
    "clear",
    "get",
    "known_ids",
    "register",
]
