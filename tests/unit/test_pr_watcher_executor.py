"""Tests for the post-PR watcher action executor.

Splits the watcher's policy from its side effects: the watcher
returns :class:`WatcherAction` records, the executor turns them into
session.yaml writebacks, plan.md follow-ups, GH PR comments, and
re-engagement subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tripwire.core.pr_watcher import (
    CommentOnPR,
    InjectFollowUp,
    ReengageAgent,
    TransitionStatus,
)
from tripwire.core.pr_watcher_executor import WatcherActionExecutor


@pytest.fixture
def project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True)
    return tmp_path


def test_execute_transition_status_writes_session_yaml(project: Path):
    from tripwire.core.session_store import load_session

    executor = WatcherActionExecutor(project_dir=project, token=None)
    executor.execute(
        TransitionStatus(
            session_id="s1",
            tripwire_id="watcher/merged_executing",
            new_status="paused",
            reason="merged",
        )
    )
    session = load_session(project, "s1")
    assert session.status == "paused"


def test_execute_inject_follow_up_appends_to_plan_md(project: Path):
    executor = WatcherActionExecutor(project_dir=project, token=None)
    executor.execute(
        InjectFollowUp(
            session_id="s1",
            tripwire_id="watcher/code_pr_no_pt_pr",
            message="## PM follow-up\n\nMissing PT PR.",
        )
    )
    text = (project / "sessions" / "s1" / "plan.md").read_text()
    assert "Missing PT PR." in text
    # Idempotent on second run.
    executor.execute(
        InjectFollowUp(
            session_id="s1",
            tripwire_id="watcher/code_pr_no_pt_pr",
            message="## PM follow-up\n\nMissing PT PR.",
        )
    )
    text2 = (project / "sessions" / "s1" / "plan.md").read_text()
    assert text2.count("Missing PT PR.") == 1


def test_execute_comment_on_pr_calls_github_api(project: Path):
    executor = WatcherActionExecutor(project_dir=project, token="ghp_xxx")
    with patch("tripwire.core.pr_watcher_executor.post_pr_comment") as mock_post:
        executor.execute(
            CommentOnPR(
                repo="ExampleOrg/example-project",
                pr_number=99,
                tripwire_id="watcher/pt_pr_missing_artifacts",
                body="missing self-review.md",
            )
        )
    mock_post.assert_called_once_with(
        "ExampleOrg/example-project",
        99,
        "missing self-review.md",
        token="ghp_xxx",
    )


def test_execute_comment_on_pr_skipped_when_no_token(project: Path):
    """No token = best-effort skip, log only — do not crash the daemon."""
    executor = WatcherActionExecutor(project_dir=project, token=None)
    with patch("tripwire.core.pr_watcher_executor.post_pr_comment") as mock_post:
        executor.execute(
            CommentOnPR(
                repo="ExampleOrg/example-project",
                pr_number=99,
                tripwire_id="watcher/pt_pr_missing_artifacts",
                body="missing self-review.md",
            )
        )
    mock_post.assert_not_called()


def test_execute_reengage_agent_invokes_pause_and_resume(project: Path):
    executor = WatcherActionExecutor(project_dir=project, token=None)
    with patch("tripwire.core.pr_watcher_executor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        executor.execute(
            ReengageAgent(session_id="s1", reason="watcher/code_pr_no_pt_pr")
        )
    cmds = [call.args[0] for call in mock_run.call_args_list]
    # At least: tripwire session pause s1, tripwire session spawn s1 --resume
    flat = [" ".join(c) for c in cmds]
    assert any("session pause s1" in c for c in flat)
    assert any("session spawn s1" in c and "--resume" in c for c in flat)
