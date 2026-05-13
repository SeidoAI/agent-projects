"""Unit tests for ``tripwire.core.workflow.side_effects`` (WS2)."""

from __future__ import annotations

from pathlib import Path


def test_registry_exposes_all_v013_handler_ids() -> None:
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


def test_get_returns_none_for_unknown_id() -> None:
    from tripwire.core.workflow.side_effects import get

    assert get("does_not_exist") is None


def test_each_registered_handler_is_callable() -> None:
    from tripwire.core.workflow.side_effects import get, known_ids

    for handler_id in known_ids():
        effect = get(handler_id)
        assert effect is not None
        assert effect.id == handler_id
        assert callable(effect.apply)
        if effect.inverse is not None:
            assert callable(effect.inverse)


def test_idempotent_handlers_skip_inverse() -> None:
    """Best-effort handlers (gh-bound, network, fs deletion) declare
    ``idempotent=True`` and the executor must not invoke their inverse.
    Only ``sweep_issues_forward`` carries an inverse today."""
    from tripwire.core.workflow.side_effects import get, known_ids

    invertible = {h for h in known_ids() if get(h).inverse is not None}  # type: ignore[union-attr]
    assert "sweep_issues_forward" in invertible


def test_register_overwrites_same_id(tmp_path: Path) -> None:
    """Registering the same id twice replaces the previous handler.
    Production code should never do this — but the registry must not
    silently swallow conflicts."""
    from tripwire.core.workflow.side_effects import (
        SideEffect,
        SideEffectContext,
        SideEffectResult,
        get,
        register,
    )

    original = get("sweep_issues_forward")
    assert original is not None

    sentinel: dict[str, bool] = {"called": False}

    def _replacement(ctx: SideEffectContext) -> SideEffectResult:
        sentinel["called"] = True
        return SideEffectResult()

    register(
        SideEffect(
            id="sweep_issues_forward",
            apply=_replacement,
            inverse=None,
            idempotent=True,
        )
    )
    try:
        replaced = get("sweep_issues_forward")
        assert replaced is not None
        assert replaced.apply is _replacement
    finally:
        register(original)


def test_unknown_status_field_lint_uses_agent_session_fields(tmp_path: Path) -> None:
    """When the validator is wired from the validator/checks/workflow.py
    site, ``preserve_fields`` paths root-validate against
    ``AgentSession.model_fields``. ``runtime_state`` resolves;
    ``bogus_field`` doesn't."""
    from textwrap import dedent

    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow import check_workflow_well_formed

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


def test_unknown_side_effect_lint_fires_with_registry(tmp_path: Path) -> None:
    """Validator wires the registry; an unregistered side-effect id is
    flagged."""
    from textwrap import dedent

    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow import check_workflow_well_formed

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


def _make_engagement_context(target_status: str, *, engagement_open: bool = True):
    """Build a minimal SideEffectContext targeting ``target_status``.

    The session carries one engagement; ``engagement_open`` toggles
    whether it has an ``ended_at`` set.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    from tripwire.core.workflow.schema import WorkflowRoute
    from tripwire.core.workflow.side_effects import SideEffectContext
    from tripwire.models.session import (
        AgentSession,
        EngagementEntry,
        RuntimeState,
        SessionStatus,
    )

    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    engagement = EngagementEntry.model_construct(
        started_at=when,
        ended_at=when.replace(hour=1) if not engagement_open else None,
        outcome="completed" if not engagement_open else None,
    )
    session = AgentSession.model_construct(
        id="s-engage",
        name="x",
        agent="backend-coder",
        issues=[],
        repos=[],
        status=SessionStatus.EXECUTING,
        runtime_state=RuntimeState.model_construct(),
        engagements=[engagement],
    )
    route = WorkflowRoute(
        id="r",
        actor="pm-agent",
        from_ref="executing",
        to_ref=target_status,
        kind="forward",
        label="x",
    )
    return SideEffectContext(
        project_dir=Path("/tmp"),
        session=session,
        route=route,
        flags={},
    )


def test_close_active_engagement_stamps_ended_at_and_outcome() -> None:
    """Target ``completed`` → ``ended_at`` set, ``outcome='completed'``,
    ``result.data['closed']=True``."""
    from tripwire.core.workflow.side_effects import get

    ctx = _make_engagement_context("completed")
    effect = get("close_active_engagement")
    assert effect is not None

    result = effect.apply(ctx)
    last = ctx.session.engagements[-1]

    assert result.data["closed"] is True
    assert last.ended_at is not None
    assert last.outcome == "completed"


def test_close_active_engagement_maps_target_to_outcome() -> None:
    """``abandoned`` and ``failed`` targets produce matching outcomes."""
    from tripwire.core.workflow.side_effects import get

    effect = get("close_active_engagement")
    assert effect is not None

    for target in ("abandoned", "failed"):
        ctx = _make_engagement_context(target)
        effect.apply(ctx)
        assert ctx.session.engagements[-1].outcome == target


def test_close_active_engagement_noop_on_non_terminal_target() -> None:
    """Targets that are not in the engagement-outcome map (e.g.
    ``in_review``) leave the engagement untouched."""
    from tripwire.core.workflow.side_effects import get

    ctx = _make_engagement_context("in_review")
    effect = get("close_active_engagement")
    assert effect is not None

    result = effect.apply(ctx)

    assert result.data == {}
    assert ctx.session.engagements[-1].ended_at is None
    assert ctx.session.engagements[-1].outcome is None


def test_close_active_engagement_noop_when_already_closed() -> None:
    """If ``last.ended_at`` is already set, leave it alone — the
    engagement was closed by a pre-executor path (e.g. ``complete_session``)
    and we must not overwrite the original timestamp."""
    from tripwire.core.workflow.side_effects import get

    ctx = _make_engagement_context("completed", engagement_open=False)
    pre_ended_at = ctx.session.engagements[-1].ended_at
    pre_outcome = ctx.session.engagements[-1].outcome

    effect = get("close_active_engagement")
    assert effect is not None
    result = effect.apply(ctx)

    assert result.data == {"closed": False}
    assert ctx.session.engagements[-1].ended_at == pre_ended_at
    assert ctx.session.engagements[-1].outcome == pre_outcome


def test_close_active_engagement_inverse_restores_pre_state() -> None:
    """After ``apply`` mutates the engagement, ``inverse`` restores the
    pre-state captured in ``result.data['pre_state']``."""
    from tripwire.core.workflow.side_effects import get

    ctx = _make_engagement_context("completed")
    effect = get("close_active_engagement")
    assert effect is not None
    assert effect.inverse is not None

    result = effect.apply(ctx)
    assert ctx.session.engagements[-1].ended_at is not None

    effect.inverse(ctx, result)

    last = ctx.session.engagements[-1]
    assert last.ended_at is None
    assert last.outcome is None


def test_known_registered_side_effect_does_not_fire_lint(tmp_path: Path) -> None:
    from textwrap import dedent

    from tripwire.core.validator._types import ValidationContext
    from tripwire.core.validator.checks.workflow import check_workflow_well_formed

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
