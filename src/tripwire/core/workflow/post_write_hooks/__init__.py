"""Inline post-write hooks invoked by the workflow executor.

The executor is an atomic primitive — no side-effect registry, no
dispatch. ``execute_transition`` calls four best-effort hooks inline
after the status write: close engagement, audit, telemetry, reset
acks. External effects (sweep, rebase, kill, draft flips, PR close,
worktree remove, follow-up stub) live as standalone scripts under
``templates/side_effects/<name>.py`` and are invoked by the executor
via subprocess. ``known_ids()`` enumerates side-effect ids the schema
may declare so the ``workflow/unknown_side_effect`` lint can flag
typos.

This package mirrors ``templates/side_effects/`` — one file per hook —
to keep symmetry between internal (inline) and external (subprocess)
side effects.
"""

from __future__ import annotations

from tripwire.core.workflow.post_write_hooks.append_audit_log_entry import (
    append_audit_record,
)
from tripwire.core.workflow.post_write_hooks.append_telemetry_row import (
    append_telemetry_record,
)
from tripwire.core.workflow.post_write_hooks.close_active_engagement import (
    close_active_engagement,
)
from tripwire.core.workflow.post_write_hooks.reset_acks import (
    reset_acks_if_requested,
)

_DECLARED_SIDE_EFFECT_IDS: frozenset[str] = frozenset(
    {
        "sweep_issues_forward",
        "rebase_pt_branch",
        "flip_drafts_to_ready",
        "flip_drafts_to_draft",
        "verify_prs_merged",
        "verify_review_ok",
        "verify_issue_artifacts",
        "kill_runtime",
        "close_open_prs",
        "remove_worktrees",
        "append_pm_followup_stub",
        "reset_acks",
        "append_audit_log_entry",
        "append_telemetry_row",
        "close_active_engagement",
    }
)


def known_ids() -> set[str]:
    """Return ids the workflow schema may declare. Static; the executor
    does not dispatch by id anymore — used by the lint to flag typos."""
    return set(_DECLARED_SIDE_EFFECT_IDS)


__all__ = [
    "append_audit_record",
    "append_telemetry_record",
    "close_active_engagement",
    "known_ids",
    "reset_acks_if_requested",
]
