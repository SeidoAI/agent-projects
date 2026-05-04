"""Workflow drift detection (KUI-124).

Drift detection queries the events log for:

- Missing required prompt-checks at a status the session passed
  through.
- Unexpected transitions (gate-bypass writes that flip session.yaml
  status without going through `tripwire transition`).
- JIT prompts that should-have-fired-but-didn't per workflow.yaml's
  status declarations.
- Heuristics that should-have-fired-but-didn't (advisory severity:
  warning, not error).

`tripwire drift report` surfaces these as findings. Empty on a clean
run; correct mismatches surfaced when steps are skipped.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner


def _project_dir(tmp_path: Path) -> Path:
    """Project with target-entry prompt-check and JIT prompt gates."""
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
                    prompt_checks: [pm-session-queue]
                    jit_prompts: [self-review]
                    heuristics: [v_stale_concept]
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
    """A `transition.completed` into a status that had a declared
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
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/prompt_check_missing" in codes


def test_drift_uses_route_controls_when_routes_declared(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

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
                  - id: queued
                    terminal: true
                    prompt_checks: [status-only-check]
                routes:
                  - id: planned-to-queued
                    actor: pm-agent
                    from: planned
                    to: queued
                    controls:
                      prompt_checks: [pm-session-queue]
            """
        ),
        encoding="utf-8",
    )

    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="queued",
        event="transition.completed",
        details={"from_status": "planned", "to_status": "queued"},
    )

    findings = detect_drift(pd, instance="test-session")
    messages = [finding.message for finding in findings]
    assert any("pm-session-queue" in message for message in messages)
    assert not any("status-only-check" in message for message in messages)


def test_drift_clears_when_prompt_check_invoked(tmp_path: Path) -> None:
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="prompt_check.invoked",
        details={"id": "pm-session-queue"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/prompt_check_missing" not in codes


def test_drift_detects_should_have_fired_jit_prompt(tmp_path: Path) -> None:
    """A target status declares a JIT prompt but was entered without
    a `jit_prompt.fired` event for it → drift."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    # Session entered executing (which declares self-review) without firing it.
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/jit_prompt_should_have_fired" in codes


def test_drift_detects_should_have_fired_heuristic(tmp_path: Path) -> None:
    """A target status declares a heuristic but was entered without a
    `heuristic.fired` event for it → drift. Severity is ``warning`` —
    heuristics are advisory, so the missed fire is a softer signal
    than the equivalent jit_prompt drift class."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    heuristic_findings = [
        f for f in findings if f.code == "drift/heuristic_should_have_fired"
    ]
    assert len(heuristic_findings) == 1
    assert heuristic_findings[0].severity == "warning"
    assert "v_stale_concept" in heuristic_findings[0].message


def test_drift_clears_heuristic_when_fired(tmp_path: Path) -> None:
    """A `heuristic.fired` event in the stay window suppresses the
    drift finding for that heuristic id."""
    from tripwire.core.events.log import emit_event
    from tripwire.core.workflow.drift import detect_drift

    pd = _project_dir(tmp_path)
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="heuristic.fired",
        details={"id": "v_stale_concept"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    findings = detect_drift(pd, instance="test-session")
    codes = [f.code for f in findings]
    assert "drift/heuristic_should_have_fired" not in codes


def test_drift_detects_unexpected_transition(tmp_path: Path) -> None:
    """If session.status currently sits at a status that's NOT reachable
    from the last `transition.completed` to_status, surface
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
        status="executing",
        event="prompt_check.invoked",
        details={"id": "pm-session-queue"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="jit_prompt.fired",
        details={"id": "self-review"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="test-session",
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
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
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
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
        status="executing",
        event="transition.completed",
        details={"from_status": "queued", "to_status": "executing"},
    )
    runner = CliRunner()
    # Filter to a clean instance — no findings.
    result = runner.invoke(
        drift_cmd,
        ["findings", "--project-dir", str(pd), "--instance", "clean"],
    )
    assert result.exit_code == 0
