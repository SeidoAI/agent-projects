"""Session-scoped post-write hooks (and the side-effect ids the
coding-session workflow may declare).

Entity-owned sub-registry. The parent
:mod:`tripwire.core.workflow.post_write_hooks` package aggregates this
plus any future entity sub-registries (``issue/``, ``pr/``,
``code_review/`` …) into a single public surface.

This module re-exports the four inline post-write hooks invoked by
:func:`tripwire.core.workflow.transitions.execute_transition` after the
status write, and declares
:data:`_DECLARED_SIDE_EFFECT_IDS` — the static set of side-effect ids
the ``coding-session`` workflow schema is allowed to reference. The
load-time ``workflow/unknown_side_effect`` lint consults the parent
package's aggregated ``known_ids()`` to flag typos.
"""

from __future__ import annotations

from tripwire.core.workflow.post_write_hooks.session.append_audit_log_entry import (
    append_audit_record,
)
from tripwire.core.workflow.post_write_hooks.session.append_telemetry_row import (
    append_telemetry_record,
)
from tripwire.core.workflow.post_write_hooks.session.close_active_engagement import (
    close_active_engagement,
)
from tripwire.core.workflow.post_write_hooks.session.reset_acks import (
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
    """Return ids the ``coding-session`` workflow schema may declare."""
    return set(_DECLARED_SIDE_EFFECT_IDS)


__all__ = [
    "append_audit_record",
    "append_telemetry_record",
    "close_active_engagement",
    "known_ids",
    "reset_acks_if_requested",
]
