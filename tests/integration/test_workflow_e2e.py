"""End-to-end smoke for the v0.9 workflow substrate.

Drives a fixture session through the full coding-session lifecycle
(planned → queued → executing → in_review → verified → completed)
using only ``tripwire transition``. Verifies that:

  - every transition emits the requested+completed pair,
  - the events log records every step,
  - drift report is empty on a clean run,
  - a deliberately-skipped step surfaces the right drift code,
  - gate rejections produce the right structured `reason`.

The test mocks ``validate_project`` (the gate's filesystem check) to
return clean — the surface itself is exercised by the unit tests for
KUI-110/KUI-119/KUI-120; this test is about the workflow-level glue.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner


def _project_dir(tmp_path: Path) -> Path:
    """Init a minimal project + a coding-session workflow."""
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
                stations:
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
    sessions_dir = tmp_path / "sessions" / "e2e-session"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "session.yaml").write_text(
        "---\n"
        "uuid: 22222222-2222-4222-8222-222222222222\n"
        "id: e2e-session\n"
        "name: E2E session\n"
        "agent: backend-coder\n"
        "issues: []\n"
        "repos: []\n"
        "status: planned\n"
        "created_at: 2026-04-30T00:00:00Z\n"
        "updated_at: 2026-04-30T00:00:00Z\n"
        "---\n",
        encoding="utf-8",
    )
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
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    return tmp_path


@pytest.fixture
def clean_validator(monkeypatch):
    from tripwire.core.validator._types import ValidationReport

    def _clean(*args, **kwargs):
        return ValidationReport(exit_code=0, errors=[], warnings=[])

    monkeypatch.setattr("tripwire.cli.transition.validate_project", _clean)
    return _clean


def test_full_lifecycle_drives_via_transition_only(
    tmp_path: Path, clean_validator
) -> None:
    """Drive planned → completed using `tripwire transition` only."""
    from tripwire.cli.drift import drift_cmd
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()

    stations = ["queued", "executing", "in_review", "verified", "completed"]
    for target in stations:
        result = runner.invoke(
            transition_cmd, ["e2e-session", target, "--project-dir", str(pd)]
        )
        assert result.exit_code == 0, (
            f"transition to {target!r} failed:\n{result.output}"
        )

    # Session reached `completed`.
    session_yaml = (pd / "sessions" / "e2e-session" / "session.yaml").read_text()
    assert "status: completed" in session_yaml
    assert "coding-session:e2e-session:completed:1" in session_yaml

    # Every transition pair recorded in the events log.
    events = list(read_events(pd, instance="e2e-session"))
    completed = [e for e in events if e["event"] == "transition.completed"]
    assert len(completed) == 5
    assert [e["details"]["to_station"] for e in completed] == stations

    # Drift report is clean.
    drift = runner.invoke(drift_cmd, ["report", "--project-dir", str(pd)])
    assert drift.exit_code == 0, drift.output
    assert "no drift" in drift.output.lower()


def test_unreachable_target_emits_structured_reason(
    tmp_path: Path,
) -> None:
    """Trying to skip stations produces `transition_not_reachable`."""
    from tripwire.cli.transition import transition_cmd
    from tripwire.core.events.log import read_events

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        transition_cmd,
        ["e2e-session", "completed", "--project-dir", str(pd)],
    )
    assert result.exit_code != 0
    rejected = list(
        read_events(pd, instance="e2e-session", event="transition.rejected")
    )
    assert len(rejected) == 1
    assert rejected[0]["details"]["reason"].startswith("transition_not_reachable")


def test_drift_surfaces_when_required_step_skipped(tmp_path: Path) -> None:
    """A workflow.yaml with a declared prompt-check on `queued` produces
    a `drift/prompt_check_missing` finding once the session leaves
    `queued` without that prompt-check."""
    from tripwire.cli.drift import drift_cmd
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    # Replace workflow.yaml with one declaring a required prompt-check
    # that we then deliberately skip.
    (pd / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                stations:
                  - id: planned
                    next: queued
                  - id: queued
                    next: executing
                    prompt_checks: [pm-session-queue]
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
    # Simulate the session leaving `queued` without invoking pm-session-queue.
    emit_event(
        pd,
        workflow="coding-session",
        instance="e2e-session",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    runner = CliRunner()
    result = runner.invoke(
        drift_cmd,
        ["report", "--project-dir", str(pd), "--instance", "e2e-session"],
    )
    assert result.exit_code != 0
    assert "drift/prompt_check_missing" in result.output
