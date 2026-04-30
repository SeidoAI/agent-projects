"""Workflow drift detection (KUI-124).

Drift detection queries the events log for:

- Missing required prompt-checks at a station the session passed
  through.
- Unexpected transitions (gate-bypass writes that flip session.yaml
  status without going through `tripwire transition`).
- Tripwires that should-have-fired-but-didn't per workflow.yaml's
  station declarations.

`tripwire drift report` surfaces these as findings. Empty on a clean
run; correct mismatches surfaced when steps are skipped.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner


def _project_dir(tmp_path: Path) -> Path:
    """Project with a coding-session workflow declaring a prompt-check
    + a tripwire on `executing`."""
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
                    prompt_checks: [pm-session-queue]
                  - id: executing
                    next: in_review
                    tripwires: [self-review]
                  - id: in_review
                    next: verified
                    prompt_checks: [pm-session-review]
                  - id: verified
                    next: completed
                  - id: completed
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_drift_report_empty_on_clean_run(tmp_path: Path) -> None:
    """No events emitted means no drift to detect — empty report."""
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    findings = detect_drift(pd, instance="test-session")
    assert findings == []


def test_drift_detects_missing_prompt_check(tmp_path: Path) -> None:
    """A `transition.completed` from a station that had a declared
    prompt-check but no `prompt_check.invoked` event for it produces
    a `drift/prompt_check_missing` finding."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    # Session moved queued → executing without invoking pm-session-queue.
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/prompt_check_missing" in codes


def test_drift_clears_when_prompt_check_invoked(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="queued",
        event="prompt_check.invoked",
        details={"id": "pm-session-queue"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/prompt_check_missing" not in codes


def test_drift_detects_should_have_fired_tripwire(tmp_path: Path) -> None:
    """A station declares a tripwire; the session left that station
    without a `tripwire.fired` event for it → drift."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    # Session left executing (which declares self-review tripwire) without
    # firing it.
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="in_review",
        event="transition.completed",
        details={"from_station": "executing", "to_station": "in_review"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/tripwire_should_have_fired" in codes


def test_drift_detects_unexpected_transition(tmp_path: Path) -> None:
    """If session.status currently sits at a station that's NOT reachable
    from the last `transition.completed` to_station, surface
    `drift/unexpected_transition`. Simulates a gate-bypass write that
    flipped session.yaml without going through `tripwire transition`."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    # Last transition.completed was queued → executing. session.yaml
    # claims status: completed (skipping in_review and verified).
    sessions_dir = pd / "sessions" / "test-session"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "session.yaml").write_text(
        "---\n"
        "uuid: 11111111-1111-4111-8111-111111111111\n"
        "id: test-session\n"
        "name: Test session\n"
        "agent: backend-coder\n"
        "issues: []\n"
        "repos: []\n"
        "status: completed\n"
        "created_at: 2026-04-30T00:00:00Z\n"
        "updated_at: 2026-04-30T00:00:00Z\n"
        "---\n",
        encoding="utf-8",
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="queued",
        event="prompt_check.invoked",
        details={"id": "pm-session-queue"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="executing",
        event="tripwire.fired",
        details={"id": "self-review"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/unexpected_transition" in codes


def test_cli_drift_report_runs_clean(tmp_path: Path) -> None:
    from tripwire.cli.drift import drift_cmd

    pd = _project_dir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(drift_cmd, ["findings", "--project-dir", str(pd)])
    assert result.exit_code == 0, result.output
    # Empty drift = "clean" output.
    assert "no drift" in result.output.lower() or result.output.strip() == ""


def test_cli_drift_report_surfaces_findings(tmp_path: Path) -> None:
    from tripwire.cli.drift import drift_cmd
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    runner = CliRunner()
    result = runner.invoke(drift_cmd, ["findings", "--project-dir", str(pd)])
    assert result.exit_code != 0
    # The CLI must mention the drift code(s) so the agent can act.
    assert "drift/prompt_check_missing" in result.output


def test_cli_drift_report_filters_by_instance(tmp_path: Path) -> None:
    from tripwire.cli.drift import drift_cmd
    from tripwire.core.events.log import emit_event

    pd = _project_dir(tmp_path)
    # Two sessions; only one has drift.
    emit_event(
        pd,
        workflow="coding-session",
        instance="dirty",
        station="executing",
        event="transition.completed",
        details={"from_station": "queued", "to_station": "executing"},
    )
    runner = CliRunner()
    # Filter to a clean instance — no findings.
    result = runner.invoke(
        drift_cmd,
        ["findings", "--project-dir", str(pd), "--instance", "clean"],
    )
    assert result.exit_code == 0
