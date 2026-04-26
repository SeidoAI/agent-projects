"""Session readiness checks (shared between queue, spawn, check)."""

import pytest

from tripwire.core.session_readiness import check_readiness


class TestCheckReadiness:
    def test_missing_session_raises(self, tmp_path_project):
        with pytest.raises(FileNotFoundError):
            check_readiness(tmp_path_project, "nonexistent", kind="check")

    def test_minimal_session_missing_plan(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", plan=False)
        report = check_readiness(tmp_path_project, "s1", kind="check")
        assert not report.ready
        errors = [i for i in report.items if not i.passing]
        assert any("plan" in i.label for i in errors)

    def test_session_with_plan_and_handoff_is_ready(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="check")
        assert report.ready

    def test_blocked_by_incomplete_sessions(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "dep", plan=True, status="planned")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            blocked_by_sessions=["dep"],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="queue")
        assert not report.ready
        blocker_items = [i for i in report.items if "dep" in i.label]
        assert len(blocker_items) > 0

    def test_blocked_by_completed_is_ok(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "dep", plan=True, status="completed")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            blocked_by_sessions=["dep"],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="queue")
        assert report.ready

    def test_done_blocker_accepted(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        """`session complete` writes status=`done` (post-v0.7.9). A
        downstream queue check must accept that as a satisfied blocker;
        otherwise we get a contradictory "wait for X to complete" error
        for sessions that already shipped."""
        save_test_session(tmp_path_project, "dep", plan=True, status="done")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            blocked_by_sessions=["dep"],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="queue")
        assert report.ready, [
            (i.label, i.severity) for i in report.items if not i.passing
        ]

    def test_verified_blocker_accepted(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        """`verified` is the post-review pre-`done` terminal-success
        state; queue must accept it too."""
        save_test_session(tmp_path_project, "dep", plan=True, status="verified")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            blocked_by_sessions=["dep"],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="queue")
        assert report.ready, [
            (i.label, i.severity) for i in report.items if not i.passing
        ]

    def test_spawn_checks_claude_on_path(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        write_handoff_yaml(tmp_path_project, "s1")
        from unittest.mock import patch

        with patch("shutil.which", return_value=None):
            report = check_readiness(tmp_path_project, "s1", kind="spawn")
        claude_items = [i for i in report.items if "claude" in i.label.lower()]
        assert len(claude_items) > 0
        assert not claude_items[0].passing
