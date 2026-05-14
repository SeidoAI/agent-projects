"""Unit tests for the v0.13 workflow executor (WS3).

The executor is a thin atomic primitive: lock → reachability →
validators → JIT prompts → prompt-checks → artifacts → status write +
inline post-write hooks → events. External side-effects (sweep, kill,
flip drafts, etc.) live as Layer-1 CLI wrappers and direct-mutation
cli paths now; the executor no longer orchestrates them.

Covers happy-path status write, preserve/clear semantics, reachability
rejection, and post-write engagement closure on terminal transitions.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def test_happy_path_writes_status_and_emits_completed(
    project_with_workflow: Path, fake_validate
) -> None:
    """A clean transition: status flips, completed event emitted, no rejected."""
    from tripwire.core.events.log import read_events
    from tripwire.core.session_store import load_session
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    assert result.status_instance == "coding-session:test-session:queued:1"

    session = load_session(project_with_workflow, "test-session")
    assert session.status.value == "queued"

    events = list(read_events(project_with_workflow, instance="test-session"))
    event_names = [e.get("event") for e in events]
    assert "transition.requested" in event_names
    assert "transition.completed" in event_names
    assert "transition.rejected" not in event_names


def test_unreachable_target_rejects_without_mutating_status(
    project_with_workflow: Path, fake_validate
) -> None:
    """Asking for a status the workflow doesn't route to fails the gate
    and leaves session.status untouched."""
    from tripwire.core.events.log import read_events
    from tripwire.core.session_store import load_session
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    # Try to transition to a status that exists but has no incoming route
    # from `planned` — add a third declared status to the workflow.
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
                  - id: completed
                    terminal: true
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    kind: forward
                  - id: queued-to-completed
                    actor: pm-agent
                    from: queued
                    to: completed
                    kind: forward
            """
        ),
        encoding="utf-8",
    )

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="completed",
    )
    assert result.ok is False
    assert "transition_not_reachable" in (result.message or "")

    session = load_session(project_with_workflow, "test-session")
    assert session.status.value == "planned"

    # Unknown target status raises (input error, not a gate verdict).
    with pytest.raises(TransitionError):
        execute_transition(
            project_with_workflow,
            instance_id="test-session",
            target_status="bogus_status",
        )

    rejected = [
        e
        for e in read_events(project_with_workflow, instance="test-session")
        if e["event"] == "transition.rejected"
    ]
    assert rejected, "expected a transition.rejected event"


def test_clear_fields_zeroes_declared_paths(
    project_with_workflow: Path, fake_validate
) -> None:
    """A route's clear_fields paths are set to None on the session."""
    from tripwire.core.session_store import load_session, save_session
    from tripwire.core.workflow.transitions import execute_transition

    # Pre-populate runtime_state so we have something to clear.
    session = load_session(project_with_workflow, "test-session")
    from tripwire.models.session import RuntimeState

    session.runtime_state = RuntimeState(claude_session_id="abc-123")
    save_session(project_with_workflow, session)

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
            """
        ),
        encoding="utf-8",
    )
    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    session = load_session(project_with_workflow, "test-session")
    assert session.runtime_state is not None
    assert session.runtime_state.claude_session_id is None


def test_preserve_fields_survives_executor_round_trip(
    project_with_workflow: Path, fake_validate
) -> None:
    """``preserve_fields`` paths retain their pre-transition values on the
    saved session. This is the PM-handoff-#5 Gap A guarantee:
    claude_session_id survives a transition that doesn't intentionally
    clear it."""
    from tripwire.core.session_store import load_session, save_session
    from tripwire.models.session import RuntimeState

    session = load_session(project_with_workflow, "test-session")
    session.runtime_state = RuntimeState(claude_session_id="preserve-me")
    save_session(project_with_workflow, session)

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
            """
        ),
        encoding="utf-8",
    )
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    session = load_session(project_with_workflow, "test-session")
    assert session.runtime_state is not None
    assert session.runtime_state.claude_session_id == "preserve-me"


def test_terminal_transition_closes_active_engagement(
    project_with_workflow: Path, fake_validate
) -> None:
    """Post-write hook: a transition to ``completed`` stamps the open
    engagement with ended_at + outcome='completed' so telemetry sees a
    non-zero duration."""
    from tripwire.core.session_store import load_session, save_session
    from tripwire.models.session import EngagementEntry

    # Rewrite workflow so planned → completed is reachable.
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
                  - id: completed
                    terminal: true
                routes:
                  - id: planned-to-completed
                    actor: pm-agent
                    from: planned
                    to: completed
                    kind: forward
            """
        ),
        encoding="utf-8",
    )
    session = load_session(project_with_workflow, "test-session")
    session.engagements.append(
        EngagementEntry(
            started_at=datetime.now(tz=timezone.utc),
            trigger="initial_launch",
        )
    )
    save_session(project_with_workflow, session)

    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="completed",
    )
    assert result.ok is True

    session = load_session(project_with_workflow, "test-session")
    last = session.engagements[-1]
    assert last.ended_at is not None
    assert last.outcome == "completed"


def test_unknown_workflow_id_raises_transition_error(
    project_with_workflow: Path, fake_validate
) -> None:
    """``workflow_id`` must match a workflow declared in workflow.yaml."""
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    with pytest.raises(TransitionError, match="not declared"):
        execute_transition(
            project_with_workflow,
            workflow_id="issue-closure",  # not declared in fixture
            instance_id="test-session",
            target_status="queued",
        )


def test_instance_id_alias_accepts_legacy_session_id_kwarg(
    project_with_workflow: Path, fake_validate
) -> None:
    """Back-compat: callers passing ``session_id=`` still work — the
    executor maps it onto ``instance_id`` internally."""
    from tripwire.core.session_store import load_session
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        project_with_workflow,
        session_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    session = load_session(project_with_workflow, "test-session")
    assert session.status.value == "queued"
