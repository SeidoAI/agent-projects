"""Tests for the in-flight monitor's action executor.

The monitor emits :class:`MonitorAction` records; the executor turns
them into side effects: SIGTERM, status writeback, plan-md follow-up
injection, monitor-log warnings.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tripwire.models.session import AgentSession
from tripwire.runtimes.monitor import (
    InjectFollowUp,
    LogWarning,
    SigtermProcess,
    TransitionStatus,
)
from tripwire.runtimes.monitor_actions import ActionExecutor


@pytest.fixture
def tmp_project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True)
    return tmp_path


def test_execute_sigterm_sends_sigterm_to_pid(tmp_project: Path):
    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    with patch("tripwire.runtimes.monitor_actions.send_sigterm") as mock_term:
        executor.execute(
            SigtermProcess(
                tripwire_id="monitor/cost_overrun",
                pid=1234,
                reason="budget exceeded",
            )
        )
    mock_term.assert_called_once_with(1234)


def test_execute_transition_status_writes_session_yaml(tmp_project: Path):
    """TransitionStatus loads, mutates, saves the session.yaml."""
    from tripwire.core.session_store import load_session

    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    executor.execute(
        TransitionStatus(
            tripwire_id="monitor/cost_overrun",
            new_status="paused",
            reason="budget exceeded",
        )
    )
    session = load_session(tmp_project, "s1")
    assert session.status == "paused"


def test_execute_transition_status_appends_engagement_outcome(tmp_project: Path):
    from tripwire.core.session_store import load_session

    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    executor.execute(
        TransitionStatus(
            tripwire_id="monitor/quota_error",
            new_status="failed",
            reason="API quota exceeded",
        )
    )
    session = load_session(tmp_project, "s1")
    assert session.status == "failed"


def test_execute_inject_follow_up_appends_to_plan_md(tmp_project: Path):
    plan = tmp_project / "sessions" / "s1" / "plan.md"
    original = plan.read_text(encoding="utf-8")
    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    executor.execute(
        InjectFollowUp(
            tripwire_id="monitor/cost_overrun",
            message="## PM follow-up — cost overrun\n\nBudget hit.",
            target="plan.md",
        )
    )
    after = plan.read_text(encoding="utf-8")
    assert original in after
    assert "## PM follow-up — cost overrun" in after
    assert "Budget hit." in after
    # Tripwire id is recorded so future agents know the source.
    assert "monitor/cost_overrun" in after


def test_execute_inject_follow_up_idempotent(tmp_project: Path):
    """Same tripwire firing twice doesn't double-write the same block."""
    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    action = InjectFollowUp(
        tripwire_id="monitor/cost_overrun",
        message="## PM follow-up — cost overrun\n\nBudget hit.",
        target="plan.md",
    )
    executor.execute(action)
    executor.execute(action)
    plan_text = (tmp_project / "sessions" / "s1" / "plan.md").read_text(
        encoding="utf-8"
    )
    assert plan_text.count("## PM follow-up — cost overrun") == 1


def test_execute_log_warning_writes_monitor_log(tmp_project: Path, tmp_path: Path):
    log_path = tmp_path / "monitor.log"
    executor = ActionExecutor(
        project_dir=tmp_project, session_id="s1", monitor_log_path=log_path
    )
    executor.execute(
        LogWarning(
            tripwire_id="monitor/key_files_drift",
            message="commits touched files outside scope",
        )
    )
    text = log_path.read_text(encoding="utf-8")
    assert "monitor/key_files_drift" in text
    assert "commits touched files outside scope" in text


def test_execute_sigterm_records_engagement_outcome(tmp_project: Path):
    """A SIGTERM tripwire stamps the active engagement outcome so post-mortem
    bookkeeping can see why the agent was killed."""
    from tripwire.core.session_store import load_session, save_session
    from datetime import datetime, timezone
    from tripwire.models.session import EngagementEntry

    session = load_session(tmp_project, "s1")
    session.engagements.append(
        EngagementEntry(started_at=datetime.now(tz=timezone.utc), trigger="initial_launch")
    )
    save_session(tmp_project, session)
    executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
    with patch("tripwire.runtimes.monitor_actions.send_sigterm"):
        executor.execute(
            SigtermProcess(
                tripwire_id="monitor/cost_overrun",
                pid=1234,
                reason="budget exceeded",
            )
        )
    after = load_session(tmp_project, "s1")
    last = after.engagements[-1]
    assert last.outcome is not None
    assert "cost_overrun" in last.outcome
