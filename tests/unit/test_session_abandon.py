"""`tripwire session abandon` (v0.7.9 §A4).

`abandoned` is the terminal status for sessions that can't reach
`done`. The behaviour: kill runtime, close OPEN PRs (skip merged
ones), remove worktrees, transition. Issues are NOT closed as
`done`.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_abandon import (
    AbandonError,
    abandon_session,
)

# ----------------------------------------------------------------------------
# Core: abandon_session
# ----------------------------------------------------------------------------


def test_abandon_planned_session_transitions_status(
    tmp_path_project: Path, save_test_session
):
    """No runtime, no worktrees — abandon still has to flip status."""
    save_test_session(tmp_path_project, "s1", status="planned")
    result = abandon_session(tmp_path_project, "s1")
    assert result.session_id == "s1"
    assert result.runtime_killed is False
    assert result.prs_closed == []
    assert result.worktrees_removed == []

    from tripwire.core.session_store import load_session

    session = load_session(tmp_path_project, "s1")
    assert session.status == "abandoned"


def test_abandon_refuses_already_terminal(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="done")
    with pytest.raises(AbandonError) as exc:
        abandon_session(tmp_path_project, "s1")
    assert exc.value.code == "abandon/already_terminal"


def test_abandon_refuses_already_abandoned(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="abandoned")
    with pytest.raises(AbandonError) as exc:
        abandon_session(tmp_path_project, "s1")
    assert exc.value.code == "abandon/already_terminal"


def test_abandon_does_not_close_issues_as_done(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    """Critical contract: abandoning a session must not mark its
    issues `done`. The whole point of `abandoned` is that the work
    didn't ship."""
    save_test_issue(tmp_path_project, "TMP-1", status="in_progress")
    save_test_session(tmp_path_project, "s1", status="planned", issues=["TMP-1"])

    abandon_session(tmp_path_project, "s1")

    from tripwire.core.store import load_issue

    issue = load_issue(tmp_path_project, "TMP-1")
    assert issue.status == "in_progress"  # unchanged


def test_abandon_paused_session_skips_runtime_kill(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """Only `executing` sessions need the runtime kill step."""
    save_test_session(tmp_path_project, "s1", status="paused")

    # If the runtime path were taken, this would raise on import.
    def _fail_if_called(*a, **k):
        raise AssertionError("runtime path should not be entered for paused")

    from tripwire.core import session_abandon as mod

    monkeypatch.setattr(
        mod, "_close_pr_for_branch", lambda *a, **k: mod._PrCloseVerdict()
    )

    result = abandon_session(tmp_path_project, "s1")
    assert result.runtime_killed is False


def test_abandon_closes_open_pr_skips_merged_pr(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """For each worktree branch: open PRs get closed, merged ones
    are recorded as skipped (closing a merged PR is meaningless)."""
    from tripwire.models.session import RuntimeState, WorktreeEntry

    rs = RuntimeState(
        worktrees=[
            WorktreeEntry(
                repo="SeidoAI/code",
                clone_path=str(tmp_path_project / "code"),
                worktree_path=str(tmp_path_project / "code-wt-s1"),
                branch="feat/s1",
            ),
            WorktreeEntry(
                repo="proj-tracking",
                clone_path=str(tmp_path_project / "proj"),
                worktree_path=str(tmp_path_project / "proj-wt-s1"),
                branch="proj/s1",
            ),
        ]
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="paused",
        runtime_state=rs.model_dump(),
    )

    from tripwire.core import session_abandon as mod

    # First branch: one open PR → close it. Second branch: merged.
    state_by_branch = {
        "feat/s1": [{"number": 11, "state": "OPEN"}],
        "proj/s1": [{"number": 22, "state": "MERGED"}],
    }

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "list"]:
            branch = cmd[cmd.index("--head") + 1]
            payload = state_by_branch.get(branch, [])

            class _R:
                returncode = 0
                stdout = __import__("json").dumps(payload)
                stderr = ""

            return _R()
        if cmd[:3] == ["gh", "pr", "close"]:

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()
        raise AssertionError(f"unexpected gh call: {cmd}")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    # Worktree-remove no-op (nothing on disk to remove).
    monkeypatch.setattr(mod, "worktree_remove", lambda *a, **k: None)

    result = abandon_session(tmp_path_project, "s1")
    assert result.prs_closed == [11]
    assert result.prs_skipped_merged == [22]


def test_abandon_pr_close_failure_is_recorded_not_raised(
    tmp_path_project: Path, save_test_session, monkeypatch
):
    """gh failures must not block the status transition. They surface
    as warnings in the result; the session still ends up abandoned."""
    from tripwire.models.session import RuntimeState, WorktreeEntry

    rs = RuntimeState(
        worktrees=[
            WorktreeEntry(
                repo="SeidoAI/code",
                clone_path=str(tmp_path_project / "code"),
                worktree_path=str(tmp_path_project / "code-wt-s1"),
                branch="feat/s1",
            )
        ]
    )
    save_test_session(
        tmp_path_project, "s1", status="paused", runtime_state=rs.model_dump()
    )

    from tripwire.core import session_abandon as mod

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return _R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "worktree_remove", lambda *a, **k: None)

    result = abandon_session(tmp_path_project, "s1")
    assert result.errors  # captured
    # Status flipped despite the error.
    from tripwire.core.session_store import load_session

    assert load_session(tmp_path_project, "s1").status == "abandoned"


def test_abandon_records_engagement_outcome(tmp_path_project: Path, save_test_session):
    from datetime import datetime, timezone

    save_test_session(
        tmp_path_project,
        "s1",
        status="paused",
        engagements=[
            {
                "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                "trigger": "initial_launch",
            }
        ],
    )
    abandon_session(tmp_path_project, "s1")

    from tripwire.core.session_store import load_session

    session = load_session(tmp_path_project, "s1")
    assert session.engagements[-1].outcome == "abandoned"
    assert session.engagements[-1].ended_at is not None


# ----------------------------------------------------------------------------
# CLI surface
# ----------------------------------------------------------------------------


def test_cli_abandon_happy_path(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="planned")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd, ["abandon", "s1", "--project-dir", str(tmp_path_project)]
    )
    assert result.exit_code == 0, result.output
    assert "abandoned" in result.output


def test_cli_abandon_unknown_session(tmp_path_project: Path):
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["abandon", "no-such", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_cli_abandon_already_done_refuses(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="done")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd, ["abandon", "s1", "--project-dir", str(tmp_path_project)]
    )
    assert result.exit_code != 0
    assert "already_terminal" in result.output or "already" in result.output
