"""Tests for tripwire.ui.services.session_service."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tripwire.core import paths
from tripwire.ui.services.session_service import (
    SessionDetail,
    SessionSummary,
    TaskProgress,
    _parse_task_checklist,
    get_session,
    list_sessions,
)

# ---------------------------------------------------------------------------
# Task-checklist parsing
# ---------------------------------------------------------------------------


class TestParseTaskChecklist:
    def test_empty(self):
        assert _parse_task_checklist("") == TaskProgress(done=0, total=0)

    def test_table_form(self):
        text = (
            "| # | Description | Status |\n"
            "|---|-------------|--------|\n"
            "| 1 | First       | done   |\n"
            "| 2 | Second      | todo   |\n"
            "| 3 | Third       | done   |\n"
        )
        assert _parse_task_checklist(text) == TaskProgress(done=2, total=3)

    def test_checkbox_form(self):
        text = "- [x] finished\n- [ ] pending\n- [x] also done\n"
        assert _parse_task_checklist(text) == TaskProgress(done=2, total=3)

    def test_zero_zero_when_unrecognisable(self):
        text = "# Just a heading\nSome prose.\n"
        assert _parse_task_checklist(text) == TaskProgress(done=0, total=0)


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_empty_when_no_sessions(self, tmp_path_project: Path):
        assert list_sessions(tmp_path_project) == []

    def test_returns_all(self, tmp_path_project: Path, save_test_session):
        save_test_session(tmp_path_project, "session-a")
        save_test_session(tmp_path_project, "session-b")

        result = list_sessions(tmp_path_project)
        assert {s.id for s in result} == {"session-a", "session-b"}
        assert all(isinstance(s, SessionSummary) for s in result)

    def test_filter_by_status(self, tmp_path_project: Path, save_test_session):
        save_test_session(tmp_path_project, "a", status="planned")
        save_test_session(tmp_path_project, "b", status="active")

        result = list_sessions(tmp_path_project, status="active")
        assert [s.id for s in result] == ["b"]

    def test_skips_hidden_dirs(self, tmp_path_project: Path, save_test_session):
        save_test_session(tmp_path_project, "real")
        # Create a .hidden session-shaped dir — should be ignored
        hidden = paths.sessions_dir(tmp_path_project) / ".hidden"
        hidden.mkdir()
        (hidden / paths.SESSION_FILENAME).write_text(
            "---\nid: .hidden\nname: x\nagent: x\n---\n"
        )

        result = list_sessions(tmp_path_project)
        assert [s.id for s in result] == ["real"]

    def test_skips_broken_session_with_warning(
        self,
        tmp_path_project: Path,
        save_test_session,
        caplog: pytest.LogCaptureFixture,
    ):
        save_test_session(tmp_path_project, "good")
        # Create a broken session.yaml (invalid frontmatter)
        bad_dir = paths.sessions_dir(tmp_path_project) / "bad"
        bad_dir.mkdir()
        (bad_dir / paths.SESSION_FILENAME).write_text("this is not valid frontmatter\n")

        with caplog.at_level(
            logging.WARNING, logger="tripwire.ui.services.session_service"
        ):
            result = list_sessions(tmp_path_project)

        assert [s.id for s in result] == ["good"]
        assert "Parse error" in caplog.text or "Schema error" in caplog.text

    def test_task_progress_populated(
        self,
        tmp_path_project: Path,
        save_test_session,
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        checklist = (
            "| # | Description | Status |\n"
            "|---|-------------|--------|\n"
            "| 1 | a           | done   |\n"
            "| 2 | b           | todo   |\n"
        )
        paths.session_artifacts_dir(tmp_path_project, "s1").mkdir(
            parents=True, exist_ok=True
        )
        (
            paths.session_artifacts_dir(tmp_path_project, "s1") / "task-checklist.md"
        ).write_text(checklist)

        [summary] = list_sessions(tmp_path_project)
        assert summary.task_progress.done == 1
        assert summary.task_progress.total == 2


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_returns_detail(self, tmp_path_project: Path, save_test_session):
        save_test_session(tmp_path_project, "s1", plan=True)
        detail = get_session(tmp_path_project, "s1")

        assert isinstance(detail, SessionDetail)
        assert detail.id == "s1"
        assert detail.plan_md.startswith("# Plan")

    def test_plan_missing_returns_empty_string(
        self, tmp_path_project: Path, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", plan=False)
        detail = get_session(tmp_path_project, "s1")
        assert detail.plan_md == ""

    def test_raises_file_not_found(self, tmp_path_project: Path):
        with pytest.raises(FileNotFoundError):
            get_session(tmp_path_project, "ghost")

    def test_artifact_status_reflects_manifest(
        self, tmp_path_project: Path, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", plan=True)

        # Manifest shipped by tmp_path_project declares "plan" (file: plan.md).
        detail = get_session(tmp_path_project, "s1")
        assert detail.artifact_status["plan"] == "present"

    def test_artifact_status_missing_when_file_absent(
        self, tmp_path_project: Path, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", plan=False)
        detail = get_session(tmp_path_project, "s1")
        assert detail.artifact_status["plan"] == "missing"

    def test_engagements_empty_in_v1(self, tmp_path_project: Path, save_test_session):
        save_test_session(tmp_path_project, "s1")
        detail = get_session(tmp_path_project, "s1")
        assert detail.engagements == []

    def test_engagements_hardcoded_empty_even_when_session_has_entries(
        self, tmp_path_project: Path, save_test_session
    ):
        # Per KUI-18 execution constraint, engagements[] is a v2-runtime
        # placeholder — always empty on the DTO even if session.yaml has
        # entries from legacy runs.
        save_test_session(
            tmp_path_project,
            "s1",
            engagements=[
                {"started_at": "2026-04-14T10:00:00", "trigger": "launch"},
                {"started_at": "2026-04-14T11:00:00", "trigger": "ci_failure"},
            ],
        )
        detail = get_session(tmp_path_project, "s1")
        assert detail.engagements == []
        # re_engagement_count is a scalar count — still derived from on-disk
        # engagements so the UI can show the number without knowing shape.
        assert detail.re_engagement_count == 1

    def test_re_engagement_count(self, tmp_path_project: Path, save_test_session):
        # Three engagements → two re-engagements (the first is the initial launch)
        engagements = [
            {
                "started_at": "2026-04-14T10:00:00",
                "trigger": "launch",
            },
            {
                "started_at": "2026-04-14T11:00:00",
                "trigger": "ci_failure",
            },
            {
                "started_at": "2026-04-14T12:00:00",
                "trigger": "verifier_rejection",
            },
        ]
        save_test_session(tmp_path_project, "s1", engagements=engagements)
        [summary] = list_sessions(tmp_path_project)
        assert summary.re_engagement_count == 2

    def test_no_manifest_returns_empty_status(
        self, tmp_path: Path, save_test_session, fresh_project
    ):
        proj = fresh_project(tmp_path / "proj")
        # No manifest.yaml at all
        save_test_session(proj, "s1")
        detail = get_session(proj, "s1")
        assert detail.artifact_status == {}
