"""Unit tests for the v0.13 side-effects module.

After the WS3 atomic-primitive refactor the executor no longer
maintains a runtime registry of dispatchable side-effect handlers.
``side_effects.py`` now exposes:

- ``known_ids()`` — a static enumeration of side-effect ids the
  workflow schema may declare. Consulted by the load-time
  ``workflow/unknown_side_effect`` lint to flag typos.
- Four inline post-write helpers invoked by ``execute_transition``
  directly: ``close_active_engagement``, ``append_audit_record``,
  ``append_telemetry_record``, ``reset_acks_if_requested``.

These tests cover ``known_ids``, the lint integration through
``check_workflow_well_formed``, and the engagement-closure helper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent


def test_known_ids_includes_declared_side_effects() -> None:
    """The static set must enumerate every side-effect id the workflow
    template references so the lint doesn't fire false positives."""
    from tripwire.core.workflow.side_effects import known_ids

    expected = {
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
    assert expected.issubset(known_ids())


def test_known_ids_returns_a_set_copy() -> None:
    """Mutating the returned set must not affect subsequent calls."""
    from tripwire.core.workflow.side_effects import known_ids

    snapshot = known_ids()
    snapshot.add("new-id")
    assert "new-id" not in known_ids()


def test_unknown_side_effect_lint_fires_with_known_ids(tmp_path: Path) -> None:
    """A workflow that declares a side-effect not in ``known_ids()`` is
    flagged by the lint."""
    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow_well_formed import (
        check_workflow_well_formed,
    )

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    side_effects: [does_not_exist]
            """
        ),
        encoding="utf-8",
    )
    ctx = ValidationContext(project_dir=tmp_path)
    findings = check_workflow_well_formed(ctx)
    codes = [f.code for f in findings]
    assert "workflow/unknown_side_effect" in codes


def test_known_side_effect_does_not_fire_lint(tmp_path: Path) -> None:
    """A workflow declaring a known side-effect id passes the lint."""
    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow_well_formed import (
        check_workflow_well_formed,
    )

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    side_effects: [sweep_issues_forward]
            """
        ),
        encoding="utf-8",
    )
    ctx = ValidationContext(project_dir=tmp_path)
    findings = check_workflow_well_formed(ctx)
    codes = [f.code for f in findings]
    assert "workflow/unknown_side_effect" not in codes


def test_unknown_status_field_lint_uses_agent_session_fields(tmp_path: Path) -> None:
    """The ``workflow/unknown_status_field`` lint root-validates
    ``preserve_fields`` paths against ``AgentSession.model_fields``.
    ``runtime_state`` resolves; ``bogus_field`` doesn't."""
    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow_well_formed import (
        check_workflow_well_formed,
    )

    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              w:
                actor: a
                trigger: t
                statuses:
                  - id: a
                  - id: b
                    terminal: true
                routes:
                  - id: r
                    actor: pm-agent
                    from: a
                    to: b
                    kind: forward
                    preserve_fields: [runtime_state.claude_session_id, bogus_field]
            """
        ),
        encoding="utf-8",
    )
    ctx = ValidationContext(project_dir=tmp_path)
    findings = check_workflow_well_formed(ctx)
    codes = [f.code for f in findings]
    assert "workflow/unknown_status_field" in codes


def _make_session_with_open_engagement():
    """Build a minimal AgentSession with one open engagement."""
    from tripwire.models.session import (
        AgentSession,
        EngagementEntry,
        RuntimeState,
        SessionStatus,
    )

    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    engagement = EngagementEntry.model_construct(
        started_at=when,
        ended_at=None,
        outcome=None,
    )
    return AgentSession.model_construct(
        id="s-engage",
        name="x",
        agent="backend-coder",
        issues=[],
        repos=[],
        status=SessionStatus.EXECUTING,
        runtime_state=RuntimeState.model_construct(),
        engagements=[engagement],
    )


def _make_route(to_ref: str):
    from tripwire.core.workflow.schema import WorkflowRoute

    return WorkflowRoute(
        id="r",
        actor="pm-agent",
        from_ref="executing",
        to_ref=to_ref,
        kind="forward",
        label="x",
    )


def test_close_active_engagement_stamps_ended_at_and_outcome() -> None:
    """Target ``completed`` → ``ended_at`` set, ``outcome='completed'``,
    returns True."""
    from tripwire.core.workflow.side_effects import close_active_engagement

    session = _make_session_with_open_engagement()
    route = _make_route("completed")
    modified = close_active_engagement(session, route)
    last = session.engagements[-1]

    assert modified is True
    assert last.ended_at is not None
    assert last.outcome == "completed"


def test_close_active_engagement_maps_target_to_outcome() -> None:
    """``abandoned`` and ``failed`` targets produce matching outcomes."""
    from tripwire.core.workflow.side_effects import close_active_engagement

    for target in ("abandoned", "failed"):
        session = _make_session_with_open_engagement()
        route = _make_route(target)
        modified = close_active_engagement(session, route)
        assert modified is True
        assert session.engagements[-1].outcome == target


def test_close_active_engagement_noop_on_non_terminal_target() -> None:
    """Targets not in the engagement-outcome map (e.g. ``in_review``)
    leave the engagement untouched."""
    from tripwire.core.workflow.side_effects import close_active_engagement

    session = _make_session_with_open_engagement()
    route = _make_route("in_review")
    modified = close_active_engagement(session, route)

    assert modified is False
    assert session.engagements[-1].ended_at is None
    assert session.engagements[-1].outcome is None


def test_close_active_engagement_noop_when_already_closed() -> None:
    """If ``last.ended_at`` is already set, leave it alone — the
    engagement was closed by a pre-executor path (e.g. ``complete_session``)
    and we must not overwrite the original timestamp."""
    from tripwire.core.workflow.side_effects import close_active_engagement

    session = _make_session_with_open_engagement()
    last = session.engagements[-1]
    last.ended_at = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    last.outcome = "completed"

    pre_ended_at = last.ended_at
    pre_outcome = last.outcome

    route = _make_route("completed")
    modified = close_active_engagement(session, route)

    assert modified is False
    assert session.engagements[-1].ended_at == pre_ended_at
    assert session.engagements[-1].outcome == pre_outcome


def test_close_active_engagement_noop_when_no_engagements() -> None:
    """A session with no engagement history is a no-op (returns False)."""
    from tripwire.core.workflow.side_effects import close_active_engagement
    from tripwire.models.session import AgentSession, SessionStatus

    session = AgentSession.model_construct(
        id="s",
        name="x",
        agent="backend-coder",
        issues=[],
        repos=[],
        status=SessionStatus.EXECUTING,
        engagements=[],
    )
    route = _make_route("completed")

    modified = close_active_engagement(session, route)
    assert modified is False
    assert session.engagements == []


def test_reset_acks_if_requested_returns_zero_when_flag_unset(tmp_path: Path) -> None:
    """No-op when ``flags['reset_acks']`` is unset or False."""
    from tripwire.core.workflow.side_effects import reset_acks_if_requested

    session = _make_session_with_open_engagement()
    assert reset_acks_if_requested(tmp_path, session=session, flags={}) == 0
    assert (
        reset_acks_if_requested(tmp_path, session=session, flags={"reset_acks": False})
        == 0
    )
