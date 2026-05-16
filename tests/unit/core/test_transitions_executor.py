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
    sessions_dir = tmp_path / "instances" / "sessions" / "test-session"
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


def test_other_sessions_findings_do_not_block_target_transition(
    project_with_workflow: Path, monkeypatch
) -> None:
    """Regression test for v0.13.2 #4.

    Per-route session tripwires (e.g. ``v_pr_merged_for_session``)
    iterate every session in the project. Before v0.13.2, transitioning
    session B was blocked by a finding against session A — the
    rejection message even cited A. After the fix, ``_run_gate``
    filters the validation report to findings owned by the target
    instance before checking errors.
    """
    from tripwire.core.validator._types import CheckResult, ValidationReport
    from tripwire.core.workflow.transitions import execute_transition

    # Inject a fake validate_project that returns a finding against a
    # DIFFERENT session id (not the one being transitioned).
    def _fake_validate(*args, **kwargs):
        return ValidationReport(
            exit_code=2,
            errors=[
                CheckResult(
                    code="session/pr_not_merged",
                    severity="error",
                    file="instances/sessions/other-session/session.yaml",
                    message="Session 'other-session' has unmerged PR.",
                )
            ],
            warnings=[],
            fixed=[],
        )

    monkeypatch.setattr("tripwire.cli.transition.validate_project", _fake_validate)

    # Add a route-level tripwire so the gate calls validate_project.
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
                    controls:
                      tripwires:
                        - v_pr_merged_for_session
            """
        ),
        encoding="utf-8",
    )

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    # The finding cited "other-session"; the target is "test-session".
    # After v0.13.2 scoping, the report has no errors for this target.
    assert result.ok is True, (
        f"transitioning 'test-session' was blocked by a finding against "
        f"'other-session': reason={result.reason!r} message={result.message!r}. "
        f"v0.13.2 #4 regression: gate must filter findings to the target instance."
    )


def test_telemetry_fires_only_on_completed_transition(
    project_with_workflow: Path, fake_validate, monkeypatch
) -> None:
    """Regression test for v0.13.2 #3.

    ``append_telemetry_record`` must fire only when transitioning TO
    ``completed`` — telemetry rows represent finished sessions. The
    v0.13.1 code path gated only on workflow id (coding-session), so
    every transition fired a row: a typical session wrote ~5 rows
    (planned→queued→…→completed), each carrying cumulative cost +
    hardcoded ``merged=True``. ``queue_runner._recent_spend_usd``
    summed ~Nx actual spend, tripping false `cap_usd_per_window`
    rejections; analyze-routing's $/merged-PR was inflated.
    """
    from tripwire.core.workflow.transitions import execute_transition

    calls: list[str] = []

    def _record(project_dir, *, session) -> None:
        calls.append(session.status.value)

    monkeypatch.setattr(
        "tripwire.core.workflow.side_effects.append_telemetry_record",
        _record,
    )

    # Non-completed transition: planned → queued (the default fixture).
    # Telemetry MUST NOT fire.
    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    assert calls == [], (
        f"telemetry fired on non-completed transition: status set to {calls!r}. "
        "v0.13.2 #3 regression — gate must check route.to_ref == 'completed'."
    )


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


# ---------------------------------------------------------------------------
# B10 — phase-advancement workflow
# ---------------------------------------------------------------------------


def test_phase_advancement_transition_flips_project_phase(
    tmp_path: Path, fake_validate
) -> None:
    """End-to-end happy path for a non-coding-session workflow.

    The phase-advancement workflow declares ``project.yaml`` as its
    instance storage. Driving the executor with
    ``workflow_id='phase-advancement'`` must flip the project's
    ``phase`` field via the generic dict-based loader/saver — no
    AgentSession plumbing involved.

    This replaces an earlier test that pinned the legacy "load_session
    fails for non-coding-session workflows" behaviour. Now that step 8
    wires :mod:`instance_io` into the executor, that legacy contract is
    intentionally broken; this test asserts the new working contract.
    """
    import yaml

    # Minimal project with phase-advancement declared. No session
    # required — the workflow's instance is project.yaml itself.
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n"
        "phase: scoping\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              phase-advancement:
                actor: pm-agent
                trigger: command.pm-phase
                instance:
                  storage_path: project.yaml
                  status_field: phase
                  status_enum: [scoping, scoped]
                  instance_id_field: name
                statuses:
                  - id: scoping
                  - id: scoped
                    terminal: true
                routes:
                  - id: advance-to-scoped
                    actor: pm-agent
                    from: scoping
                    to: scoped
                    kind: forward
            """
        ),
        encoding="utf-8",
    )

    from tripwire.core.events.log import read_events
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        tmp_path,
        workflow_id="phase-advancement",
        instance_id="test",
        target_status="scoped",
    )
    assert result.ok is True
    assert result.status_instance == "phase-advancement:test:scoped:1"

    project_data = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert project_data["phase"] == "scoped"
    assert project_data["current_status_instance"] == "phase-advancement:test:scoped:1"

    events = list(read_events(tmp_path, workflow="phase-advancement", instance="test"))
    event_names = [e.get("event") for e in events]
    assert "transition.requested" in event_names
    assert "transition.completed" in event_names
    assert "transition.rejected" not in event_names


def test_issue_closure_transition_flips_issue_status_field(
    tmp_path: Path, fake_validate
) -> None:
    """End-to-end happy path for the issue-closure workflow.

    The issue-closure workflow's instance.storage_path is
    ``instances/issues/{instance_id}/issue.yaml``. The executor must
    load that file as a dict, flip its ``status`` field, and write it
    back via :func:`save_instance` — no Issue model coercion required
    at the executor layer (the instance file remains frontmatter+body).
    """
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              issue-closure:
                actor: pm-agent
                trigger: command.pm-issue-close
                instance:
                  storage_path: instances/issues/{instance_id}/issue.yaml
                  status_field: status
                  status_enum: [planned, completed]
                  instance_id_field: id
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
    issue_dir = tmp_path / "instances" / "issues" / "TST-1"
    issue_dir.mkdir(parents=True)
    (issue_dir / "issue.yaml").write_text(
        "---\nid: TST-1\ntitle: Demo issue\nstatus: planned\n---\nBody text.\n",
        encoding="utf-8",
    )

    from tripwire.core.workflow.instance_io import load_instance
    from tripwire.core.workflow.transitions import execute_transition

    result = execute_transition(
        tmp_path,
        workflow_id="issue-closure",
        instance_id="TST-1",
        target_status="completed",
    )
    assert result.ok is True
    assert result.status_instance == "issue-closure:TST-1:completed:1"

    data = load_instance(tmp_path, "issue-closure", "TST-1")
    assert data["status"] == "completed"
    assert data["current_status_instance"] == "issue-closure:TST-1:completed:1"
    # Body survives the round-trip — frontmatter+body shape is preserved
    # by save_instance.
    assert data.get("body", "").strip() == "Body text."


def test_unknown_workflow_instance_raises_transition_error(
    tmp_path: Path, fake_validate
) -> None:
    """When a declared non-coding-session workflow has no instance file
    on disk, the executor wraps the underlying not-found error in a
    structured :class:`TransitionError`. Parallels the coding-session
    "session 'foo' not found" error contract."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              issue-closure:
                actor: pm-agent
                trigger: command.pm-issue-close
                instance:
                  storage_path: instances/issues/{instance_id}/issue.yaml
                  status_field: status
                  status_enum: [planned, completed]
                  instance_id_field: id
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

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    with pytest.raises(TransitionError, match="not found"):
        execute_transition(
            tmp_path,
            workflow_id="issue-closure",
            instance_id="TST-404",
            target_status="completed",
        )


def test_project_config_carries_current_status_instance_field() -> None:
    """B10: ``ProjectConfig.current_status_instance`` is the workflow
    status-instance id for the project's role as the phase-advancement
    instance. Defaults to ``None`` so existing project.yaml files load
    cleanly; the executor back-fills on first transition (step 8).
    """
    from tripwire.models.project import ProjectConfig

    config = ProjectConfig(name="t", key_prefix="T")
    assert config.current_status_instance is None
    config.current_status_instance = "phase-advancement:t:scoped:1"
    assert config.current_status_instance == "phase-advancement:t:scoped:1"


def test_executor_resolves_workflow_once(
    project_with_workflow: Path, fake_validate, monkeypatch
) -> None:
    """``execute_transition`` must parse ``workflow.yaml`` exactly once.

    Pre-refactor: pre-lock load, in-lock load, save, and (optionally) the
    engagement-close save each called ``load_workflows`` via the generic
    dict loader — 3-5 parses per transition. The executor now threads
    the pre-resolved :class:`Workflow` through ``_load_workflow_instance``
    and ``_save_workflow_instance`` so the single parse at the top of
    :func:`execute_transition` is the only one.

    The coding-session path round-trips through the typed session store
    (not :func:`load_instance`), so for this path the only loader call
    is the executor's own at the top. We assert that, and pair it with a
    parallel non-coding-session check in the second body of the test.
    """
    from tripwire.core.workflow import transitions as transitions_mod
    from tripwire.core.workflow.transitions import execute_transition

    real_loader = transitions_mod.load_workflows
    calls = {"n": 0}

    def _spy(project_dir):
        calls["n"] += 1
        return real_loader(project_dir)

    monkeypatch.setattr(transitions_mod, "load_workflows", _spy)

    result = execute_transition(
        project_with_workflow,
        instance_id="test-session",
        target_status="queued",
    )
    assert result.ok is True
    # Exactly one parse: the executor's own at the top.
    assert calls["n"] == 1, (
        f"expected load_workflows to be called once per transition, got {calls['n']}"
    )


def test_executor_resolves_workflow_once_for_dict_instance(
    tmp_path: Path, fake_validate, monkeypatch
) -> None:
    """As above, but for a non-coding-session workflow whose instance
    round-trips through the generic dict loader/saver. This is the path
    where pre-refactor we paid for 3+ ``load_workflows`` calls:
    pre-lock ``load_instance`` (1), in-lock ``load_instance`` (1), and
    the final ``save_instance`` (1). All three must now reuse the
    pre-resolved workflow.
    """
    # Plant a minimal dict-backed workflow with one route + one instance.
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
              demo:
                actor: pm-agent
                trigger: demo.start
                instance:
                  storage_path: instances/demos/{instance_id}/demo.yaml
                  status_field: status
                  status_enum: [planned, queued]
                  required_fields: [id, status]
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
    instance_dir = tmp_path / "instances" / "demos" / "d1"
    instance_dir.mkdir(parents=True)
    (instance_dir / "demo.yaml").write_text(
        "id: d1\nstatus: planned\n", encoding="utf-8"
    )

    from tripwire.core.workflow import transitions as transitions_mod
    from tripwire.core.workflow.transitions import execute_transition

    real_loader = transitions_mod.load_workflows
    calls = {"n": 0}

    def _spy(project_dir):
        calls["n"] += 1
        return real_loader(project_dir)

    monkeypatch.setattr(transitions_mod, "load_workflows", _spy)

    # Also patch the loader as seen by instance_io — that's the module
    # we're guarding against re-parsing. A pre-resolved workflow should
    # mean instance_io never reaches the spy.
    from tripwire.core.workflow import instance_io as io_mod

    io_calls = {"n": 0}

    def _io_spy(project_dir):
        io_calls["n"] += 1
        return real_loader(project_dir)

    monkeypatch.setattr(io_mod, "load_workflows", _io_spy)

    result = execute_transition(
        tmp_path,
        workflow_id="demo",
        instance_id="d1",
        target_status="queued",
    )
    assert result.ok is True
    # The executor parses workflow.yaml exactly once at the top.
    assert calls["n"] == 1, (
        f"expected transitions.load_workflows to be called once, got {calls['n']}"
    )
    # And instance_io must NOT re-parse it — the pre-resolved workflow
    # is threaded through every load/save.
    assert io_calls["n"] == 0, (
        f"expected instance_io.load_workflows to be called zero times when "
        f"executor threads a pre-resolved workflow, got {io_calls['n']}"
    )
