"""Unit tests for the v0.13 workflow executor (WS3).

Covers happy-path side-effect orchestration, side-effect failure
triggering rollback, and preserve_fields/clear_fields enforcement.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def project_with_workflow(tmp_path: Path):
    """Init a minimal project with a one-route workflow.yaml + session."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    side_effects: [test_effect_ok]
            """
        ),
        encoding="utf-8",
    )
    sessions_dir = tmp_path / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "session.yaml").write_text(
        "---\n"
        "uuid: 11111111-1111-4111-8111-111111111111\n"
        "id: test-session\n"
        "name: Test session\n"
        "agent: backend-coder\n"
        "issues: []\n"
        "repos: []\n"
        "status: planned\n"
        "created_at: 2026-04-30T00:00:00Z\n"
        "updated_at: 2026-04-30T00:00:00Z\n"
        "---\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fake_validate(monkeypatch):
    """Replace validate_project with a no-op that returns clean."""
    from tripwire.core.validator._types import ValidationReport

    def _ok(*args, **kwargs):
        return ValidationReport(exit_code=0, errors=[], warnings=[], fixed=[])

    monkeypatch.setattr(
        "tripwire.cli.transition.validate_project",
        _ok,
    )


@pytest.fixture(autouse=True)
def reset_test_handlers():
    """Each test registers temporary handlers; clean up afterwards."""
    from tripwire.core.workflow.side_effects import _REGISTRY

    snapshot = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


def _register_test_effect(
    effect_id: str,
    *,
    apply_fn=None,
    inverse_fn=None,
    idempotent: bool = False,
):
    """Register a temporary side-effect for one test."""
    from tripwire.core.workflow.side_effects import (
        SideEffect,
        SideEffectResult,
        register,
    )

    if apply_fn is None:
        apply_fn = lambda ctx: SideEffectResult()  # noqa: E731

    register(
        SideEffect(
            id=effect_id,
            apply=apply_fn,
            inverse=inverse_fn,
            idempotent=idempotent,
        )
    )


def test_happy_path_runs_side_effects_and_emits_completed(
    project_with_workflow: Path, fake_validate
) -> None:
    """A clean transition: status flips, side-effect runs, completed emitted."""
    from tripwire.core.events.log import read_events
    from tripwire.core.session_store import load_session
    from tripwire.core.workflow.side_effects import SideEffectResult
    from tripwire.core.workflow.transitions import execute_transition

    sentinel: dict[str, int] = {"calls": 0}

    def _apply(ctx):
        sentinel["calls"] += 1
        return SideEffectResult()

    _register_test_effect("test_effect_ok", apply_fn=_apply, idempotent=True)

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    assert sentinel["calls"] == 1

    session = load_session(project_with_workflow, "test-session")
    assert session.status.value == "queued"

    events = list(read_events(project_with_workflow, instance="test-session"))
    event_names = [e.get("event") for e in events]
    assert "transition.requested" in event_names
    assert "transition.completed" in event_names


def test_side_effect_failure_rolls_back_session_status(
    project_with_workflow: Path, fake_validate
) -> None:
    """A failing side-effect rolls back: status returns to planned, completed
    NOT emitted, rejected IS emitted."""
    from tripwire.core.events.log import read_events
    from tripwire.core.session_store import load_session
    from tripwire.core.workflow.side_effects import SideEffectFailure
    from tripwire.core.workflow.transitions import execute_transition

    def _apply_fail(ctx):
        raise SideEffectFailure("test_failure")

    _register_test_effect("test_effect_ok", apply_fn=_apply_fail, idempotent=True)

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is False
    assert "test_failure" in (result.message or "")

    session = load_session(project_with_workflow, "test-session")
    assert session.status.value == "planned"  # rolled back

    event_names = [
        e.get("event")
        for e in read_events(project_with_workflow, instance="test-session")
    ]
    assert "transition.rejected" in event_names
    assert "transition.completed" not in event_names


def test_invertible_side_effect_runs_inverse_on_subsequent_failure(
    project_with_workflow: Path, fake_validate
) -> None:
    """Two side-effects on a route, second fails — first's inverse fires."""
    from tripwire.core.workflow.side_effects import (
        SideEffect,
        SideEffectFailure,
        SideEffectResult,
        register,
    )
    from tripwire.core.workflow.transitions import execute_transition

    apply_calls = {"first": 0, "second": 0}
    inverse_calls = {"first": 0}

    def _first_apply(ctx):
        apply_calls["first"] += 1
        return SideEffectResult(data={"marker": True})

    def _first_inverse(ctx, result):
        inverse_calls["first"] += 1

    def _second_apply(ctx):
        apply_calls["second"] += 1
        raise SideEffectFailure("second_fails")

    register(
        SideEffect(
            id="test_first",
            apply=_first_apply,
            inverse=_first_inverse,
            idempotent=False,
        )
    )
    register(
        SideEffect(
            id="test_second",
            apply=_second_apply,
            inverse=None,
            idempotent=True,
        )
    )

    # Re-write the workflow to chain both effects.
    (project_with_workflow / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    side_effects: [test_first, test_second]
            """
        ),
        encoding="utf-8",
    )

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is False
    assert apply_calls == {"first": 1, "second": 1}
    assert inverse_calls == {"first": 1}


def test_idempotent_side_effect_skips_inverse_during_rollback(
    project_with_workflow: Path, fake_validate
) -> None:
    """Idempotent handlers (gh-bound, fs deletion) are NOT inverted on
    rollback — even if they declare an inverse."""
    from tripwire.core.workflow.side_effects import (
        SideEffect,
        SideEffectFailure,
        SideEffectResult,
        register,
    )
    from tripwire.core.workflow.transitions import execute_transition

    inverse_calls = {"first": 0}

    def _first_apply(ctx):
        return SideEffectResult()

    def _first_inverse(ctx, result):
        inverse_calls["first"] += 1

    def _second_apply(ctx):
        raise SideEffectFailure("boom")

    register(
        SideEffect(
            id="test_idempotent_first",
            apply=_first_apply,
            inverse=_first_inverse,
            idempotent=True,  # skipped on rollback
        )
    )
    register(
        SideEffect(
            id="test_failing_second",
            apply=_second_apply,
            inverse=None,
            idempotent=True,
        )
    )

    (project_with_workflow / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    side_effects: [test_idempotent_first, test_failing_second]
            """
        ),
        encoding="utf-8",
    )

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is False
    assert inverse_calls["first"] == 0


def test_unregistered_side_effect_id_fails_loud(
    project_with_workflow: Path, fake_validate
) -> None:
    """A workflow declaring a side-effect that isn't in the registry
    fails the transition rather than silently skipping it. (The lint
    catches this at load time normally; this test exercises the
    runtime fallback.)"""
    from tripwire.core.workflow.transitions import execute_transition

    (project_with_workflow / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    side_effects: [does_not_exist]
            """
        ),
        encoding="utf-8",
    )
    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is False
    assert "unregistered_side_effect" in (result.message or "")


def test_clear_fields_zeroes_declared_paths(
    project_with_workflow: Path, fake_validate
) -> None:
    """A route's clear_fields paths are set to None on the session."""
    from tripwire.core.session_store import load_session, save_session
    from tripwire.core.workflow.side_effects import SideEffectResult
    from tripwire.core.workflow.transitions import execute_transition

    # Pre-populate runtime_state so we have something to clear.
    session = load_session(project_with_workflow, "test-session")
    from tripwire.models.session import RuntimeState

    session.runtime_state = RuntimeState(claude_session_id="abc-123")
    save_session(project_with_workflow, session)

    _register_test_effect(
        "test_effect_ok",
        apply_fn=lambda ctx: SideEffectResult(),
        idempotent=True,
    )

    (project_with_workflow / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    clear_fields: [runtime_state.claude_session_id]
                    side_effects: [test_effect_ok]
            """
        ),
        encoding="utf-8",
    )
    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    session = load_session(project_with_workflow, "test-session")
    assert session.runtime_state is not None
    assert session.runtime_state.claude_session_id is None


def test_preserve_fields_survives_clearing_side_effect(
    project_with_workflow: Path, fake_validate
) -> None:
    """If a side-effect inadvertently zeros a preserved field, the
    executor re-asserts the pre-state value before saving. This is the
    PM-handoff-#5 Gap A guarantee: claude_session_id survives reopen."""
    from tripwire.core.session_store import load_session, save_session
    from tripwire.core.workflow.side_effects import SideEffectResult
    from tripwire.models.session import RuntimeState

    session = load_session(project_with_workflow, "test-session")
    session.runtime_state = RuntimeState(claude_session_id="preserve-me")
    save_session(project_with_workflow, session)

    def _zero_runtime(ctx):
        # Misbehaving side-effect: clears the preserved field.
        if ctx.session.runtime_state is not None:
            ctx.session.runtime_state.claude_session_id = None
        return SideEffectResult()

    _register_test_effect(
        "test_effect_ok",
        apply_fn=_zero_runtime,
        idempotent=True,
    )

    (project_with_workflow / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                  - id: queued
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                    preserve_fields: [runtime_state.claude_session_id]
                    side_effects: [test_effect_ok]
            """
        ),
        encoding="utf-8",
    )
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    session = load_session(project_with_workflow, "test-session")
    assert session.runtime_state is not None
    assert session.runtime_state.claude_session_id == "preserve-me"
