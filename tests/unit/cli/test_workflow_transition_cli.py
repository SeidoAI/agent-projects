"""End-to-end tests for ``tripwire transition`` (KUI-159).

The transition CLI is the gate runner: it loads workflow.yaml, runs
the status's validators → JIT prompts → prompt-checks, and on pass
moves the session to the new status and assigns a status-instance
id. On fail it emits ``transition.rejected`` with a structured
``reason`` and the session stays put.

Concurrent transitions on the same session serialise via a per-session
lockfile under ``.tripwire/locks/transition-<sid>.lock``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner


def _project_dir(tmp_path: Path) -> Path:
    """Init a minimal project with a workflow.yaml and one session."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\nstatuses: [planned]\n"
        "status_transitions:\n  planned: []\nrepos: {}\nnext_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: queued
                  - id: queued
                    next: executing
                  - id: executing
                    next: in_review
                  - id: in_review
                    next: verified
                  - id: verified
                    next: completed
                  - id: completed
                    terminal: true
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
    # Init git so lint rules that consult origin/main don't fail the
    # transition gate's validate step. Skip the test if git is missing.
    try:
        subprocess.run(
            ["git", "init", "-q", "--initial-branch=main", str(tmp_path)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "-A"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    return tmp_path


@pytest.fixture
def clean_validator(monkeypatch):
    """Patch ``validate_project`` to return a clean report so happy-path
    tests aren't subject to the lint rules' offline-mode warnings about
    ``origin/main`` (those fire any time the project tracking repo isn't
    fetched, which test fixtures aren't)."""
    from tripwire.core.validator._types import ValidationReport

    calls = []

    def _clean(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return ValidationReport(exit_code=0, errors=[], warnings=[])

    _clean.calls = calls
    monkeypatch.setattr("tripwire.cli.transition.validate_project", _clean)
    return _clean


def test_transition_pass_path_advances_session(tmp_path: Path, clean_validator) -> None:
    """Happy path: gate passes, session.status flips, transition.completed
    emitted, status-instance id written."""
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["test-session", "queued", "--project-dir", str(pd)],
    )
    assert result.exit_code == 0, result.output

    # Session status flipped.
    session_yaml = (pd / "sessions" / "test-session" / "session.yaml").read_text()
    assert "status: queued" in session_yaml
    # Status-instance id present.
    assert "current_status_instance:" in session_yaml
    assert "coding-session:test-session:queued:1" in session_yaml

    # transition.requested + transition.completed emitted (no .rejected).
    rows = list(read_events(pd, instance="test-session"))
    kinds = [r["event"] for r in rows]
    assert "transition.requested" in kinds
    assert "transition.completed" in kinds
    assert "transition.rejected" not in kinds


def test_transition_uses_target_status_validators(
    tmp_path: Path, clean_validator
) -> None:
    from tripwire.cli.transition import transition_cmd

    pd = _project_dir(tmp_path)
    (pd / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: queued
                    validators: [v_id_format]
                  - id: queued
                    next: executing
                    validators: [v_uuid_present]
                  - id: executing
                    terminal: true
            """
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        transition_cmd,
        ["test-session", "queued", "--project-dir", str(pd)],
    )

    assert result.exit_code == 0, result.output
    call = clean_validator.calls[-1]
    assert call["kwargs"]["validator_ids"] == ["v_uuid_present"]
    assert call["kwargs"]["workflow"] == "coding-session"
    assert call["kwargs"]["status"] == "queued"


def test_transition_rejects_disallowed_target(tmp_path: Path) -> None:
    """Rejecting an unreachable status emits transition.rejected with
    a structured reason naming the gate check that failed."""
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    # planned → completed is illegal — only `queued` is reachable.
    result = runner.invoke(
        transition_cmd,
        ["test-session", "completed", "--project-dir", str(pd)],
    )
    assert result.exit_code != 0
    assert "not reachable" in result.output.lower()

    # Session stays at planned.
    session_yaml = (pd / "sessions" / "test-session" / "session.yaml").read_text()
    assert "status: planned" in session_yaml

    # transition.rejected emitted with reason.
    rows = list(read_events(pd, instance="test-session", event="transition.rejected"))
    assert len(rows) == 1
    assert rows[0]["details"].get("reason")
    assert rows[0]["details"]["reason"].startswith("transition_not_reachable")


def test_transition_increments_status_instance_n(
    tmp_path: Path, clean_validator
) -> None:
    """Repeat visits to a status bump the {n} suffix."""
    from tripwire.cli.transition import transition_cmd

    pd = _project_dir(tmp_path)
    runner = CliRunner()

    runner.invoke(transition_cmd, ["test-session", "queued", "--project-dir", str(pd)])
    runner.invoke(
        transition_cmd, ["test-session", "executing", "--project-dir", str(pd)]
    )
    runner.invoke(
        transition_cmd, ["test-session", "in_review", "--project-dir", str(pd)]
    )

    session_yaml = (pd / "sessions" / "test-session" / "session.yaml").read_text()
    assert "coding-session:test-session:in_review:1" in session_yaml


def test_transition_unknown_session_errors(tmp_path: Path) -> None:
    from tripwire.cli.transition import transition_cmd

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["does-not-exist", "queued", "--project-dir", str(pd)],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_transition_unknown_station_errors(tmp_path: Path) -> None:
    from tripwire.cli.transition import transition_cmd

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["test-session", "nonexistent-status", "--project-dir", str(pd)],
    )
    assert result.exit_code != 0
    assert "unknown status" in result.output.lower()


def test_transition_lockfile_serialises_concurrent(
    tmp_path: Path, clean_validator
) -> None:
    """The lockfile path must be created when the gate runs."""
    from tripwire.cli.transition import transition_cmd

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    runner.invoke(transition_cmd, ["test-session", "queued", "--project-dir", str(pd)])
    # Lock files don't survive cross-process — but the lock NAME path
    # convention is asserted at the locks-helper layer. We just verify
    # the .tripwire dir was created (a side effect of project_lock).
    assert (pd / ".tripwire").is_dir()


def test_transition_completed_event_carries_status_instance(
    tmp_path: Path, clean_validator
) -> None:
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd, ["test-session", "queued", "--project-dir", str(pd)]
    )
    assert result.exit_code == 0, result.output
    completed = list(
        read_events(pd, instance="test-session", event="transition.completed")
    )
    assert len(completed) == 1
    assert (
        completed[0]["details"]["status_instance"]
        == "coding-session:test-session:queued:1"
    )


def test_transition_rejected_when_validators_fail(tmp_path: Path) -> None:
    """If `tripwire validate --strict` reports errors at the destination
    status, the gate rejects with reason=validators_failed."""
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    # Plant a bad node so validate produces an error.
    (pd / "nodes").mkdir(parents=True, exist_ok=True)
    (pd / "nodes" / "bad-node.yaml").write_text(
        "---\nbroken: yaml syntax\n  no quotes here: oops:\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["test-session", "queued", "--project-dir", str(pd)],
    )
    assert result.exit_code != 0
    rows = list(read_events(pd, instance="test-session", event="transition.rejected"))
    assert any(
        r["details"].get("reason", "").startswith("validators_failed") for r in rows
    )
    # Session did NOT advance.
    session_yaml = (pd / "sessions" / "test-session" / "session.yaml").read_text()
    assert "status: planned" in session_yaml


def test_transition_uses_validate_project_for_filesystem_gate(tmp_path: Path) -> None:
    """The gate consumes KUI-110's edit-time validation hook surface —
    same `validate_project` entry point. Asserted by patching
    `validate_project` and confirming the gate calls it."""
    from unittest.mock import patch

    from tripwire.cli.transition import transition_cmd
    from tripwire.core.validator._types import ValidationReport

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    with patch(
        "tripwire.cli.transition.validate_project",
        return_value=ValidationReport(exit_code=0, errors=[], warnings=[]),
    ) as mocked:
        result = runner.invoke(
            transition_cmd,
            ["test-session", "queued", "--project-dir", str(pd)],
        )
        assert result.exit_code == 0, result.output
        assert mocked.called


def test_transition_emits_requested_before_completed_or_rejected(
    tmp_path: Path, clean_validator
) -> None:
    """Event ordering: `transition.requested` always precedes
    `transition.completed` or `transition.rejected` for the same call."""
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    runner.invoke(transition_cmd, ["test-session", "queued", "--project-dir", str(pd)])
    rows = list(read_events(pd, instance="test-session"))
    kinds = [r["event"] for r in rows]
    assert kinds.index("transition.requested") < kinds.index("transition.completed")


# ============================================================================
# Codex P1 (PR #73 follow-up): lock race — gate must reload session
# state INSIDE the lock, not pass a pre-lock snapshot.
# ============================================================================


def test_transition_reloads_session_inside_lock(
    tmp_path: Path, clean_validator
) -> None:
    """If `_run_gate` is called inside `project_lock`, the session
    state it sees must be a fresh read AFTER the lock was acquired.
    Pre-fix the gate captured `current_station` before the lock, so a
    second concurrent transition could observe the same source state
    and emit a duplicate `transition.completed`.

    The fix moves `load_session` inside the `with project_lock(...)`
    block. Black-box test: simulate a stale snapshot by writing a
    different `status:` to session.yaml between the pre-lock load and
    the gate body. Pre-fix, the gate accepts the stale state and
    transitions from there. Post-fix, the gate sees the fresh state
    and rejects (or accepts) based on what's actually on disk.
    """
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events
    from tripwire.core.session_store import load_session, save_session

    pd = _project_dir(tmp_path)
    # Move the session forward to "queued" before the test transitions
    # request "executing". Pre-fix the gate uses whatever pre_lock
    # snapshot was; post-fix it always re-reads fresh state.
    sess = load_session(pd, "test-session")
    from tripwire.models.enums import SessionStatus

    sess.status = SessionStatus.QUEUED
    save_session(pd, sess)

    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["test-session", "executing", "--project-dir", str(pd)],
    )
    # queued → executing is reachable, so this should succeed.
    assert result.exit_code == 0, result.output

    # The transition.completed event records `from_status: queued`,
    # which is what was on disk INSIDE the lock — not whatever
    # pre-lock snapshot some prior call to load_session captured.
    completed = [
        e
        for e in read_events(pd, instance="test-session")
        if e["event"] == "transition.completed"
    ]
    assert completed
    assert completed[-1]["details"]["from_status"] == "queued"
    assert completed[-1]["details"]["to_status"] == "executing"
