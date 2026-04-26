"""Tests for the `(over budget)` flag in `tripwire session list` (KUI-92 §3.A4).

When the runtime monitor fires `monitor/cost_overrun`, three things happen
together:
  1. SIGTERM the agent (already in v0.7.9 ActionExecutor)
  2. Status flips to ``paused`` (already in v0.7.9 ActionExecutor)
  3. ``RuntimeState.cost_overrun_at`` is stamped (NEW in this session)
     so the `session list` CLI can flag it.

The combination tells a human at a glance: "this session paused because
of budget, not because someone manually paused it."
"""

from __future__ import annotations

from datetime import datetime, timezone

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session
from tripwire.models.session import RuntimeState
from tripwire.runtimes.monitor import SigtermProcess
from tripwire.runtimes.monitor_actions import ActionExecutor


def test_runtime_state_has_cost_overrun_at_field() -> None:
    """``RuntimeState`` must accept ``cost_overrun_at`` (default None)."""
    rs = RuntimeState()
    assert rs.cost_overrun_at is None
    rs2 = RuntimeState(cost_overrun_at=datetime.now(tz=timezone.utc))
    assert rs2.cost_overrun_at is not None


def test_action_executor_stamps_cost_overrun_at(
    save_test_session, tmp_path_project
) -> None:
    """When the executor handles a ``monitor/cost_overrun`` SigtermProcess,
    it stamps ``runtime_state.cost_overrun_at`` on the session yaml."""
    save_test_session(tmp_path_project, session_id="session-budget-test", plan=True)

    executor = ActionExecutor(
        project_dir=tmp_path_project,
        session_id="session-budget-test",
        monitor_log_path=tmp_path_project / "monitor.log",
    )
    # Note: the SIGTERM target pid won't match a real process; the
    # executor logs that fact but doesn't crash.
    executor.execute(
        SigtermProcess(
            tripwire_id="monitor/cost_overrun",
            pid=99999999,
            reason="over budget at $0.05",
        )
    )

    reloaded = load_session(tmp_path_project, "session-budget-test")
    assert reloaded.runtime_state.cost_overrun_at is not None


def test_action_executor_does_not_stamp_for_other_sigterm(
    save_test_session, tmp_path_project
) -> None:
    """A SigtermProcess from a non-cost tripwire (e.g. push-loop) must
    NOT stamp the cost_overrun_at field."""
    save_test_session(tmp_path_project, session_id="session-push-loop", plan=True)

    executor = ActionExecutor(
        project_dir=tmp_path_project,
        session_id="session-push-loop",
        monitor_log_path=tmp_path_project / "monitor.log",
    )
    executor.execute(
        SigtermProcess(
            tripwire_id="monitor/push_loop",
            pid=99999999,
            reason="10 consecutive failed pushes",
        )
    )

    reloaded = load_session(tmp_path_project, "session-push-loop")
    assert reloaded.runtime_state.cost_overrun_at is None


def test_session_list_table_flags_over_budget(
    save_test_session, tmp_path_project
) -> None:
    """`tripwire session list` (table format) shows ``(over budget)`` for
    every session whose ``runtime_state.cost_overrun_at`` is set, and not
    for clean paused sessions."""
    save_test_session(
        tmp_path_project,
        session_id="session-overbudget",
        status="paused",
        runtime_state={"cost_overrun_at": datetime.now(tz=timezone.utc).isoformat()},
    )
    save_test_session(
        tmp_path_project,
        session_id="session-paused-clean",
        status="paused",
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["list", "--project-dir", str(tmp_path_project), "--format", "table"],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    # The marker appears exactly once: for the over-budget row only.
    assert result.output.count("over budget") == 1
    over_line = next(
        line for line in result.output.splitlines() if "session-overbudget" in line
    )
    assert "over budget" in over_line


def test_session_list_json_includes_cost_overrun_at(
    save_test_session, tmp_path_project
) -> None:
    """`session list --format json` must surface ``cost_overrun_at`` on
    the over-budget row so machine consumers can filter."""
    import json

    save_test_session(
        tmp_path_project,
        session_id="session-overbudget-json",
        status="paused",
        runtime_state={"cost_overrun_at": datetime.now(tz=timezone.utc).isoformat()},
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["list", "--project-dir", str(tmp_path_project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    row = next(r for r in rows if r["id"] == "session-overbudget-json")
    assert row.get("over_budget") is True
