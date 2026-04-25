"""Tests for the shared task-checklist parser used by both CLI and UI."""

from __future__ import annotations

from tripwire.core.task_checklist import TaskProgress, parse_task_checklist


class TestParseTaskChecklist:
    def test_empty_text_returns_zero(self):
        assert parse_task_checklist("") == TaskProgress(done=0, total=0)

    def test_table_form_with_status_column(self):
        text = (
            "| # | Task | Status | Comments |\n"
            "|---|------|--------|----------|\n"
            "| 1 | First  | done        | — |\n"
            "| 2 | Second | in_progress | — |\n"
            "| 3 | Third  | done        | — |\n"
        )
        assert parse_task_checklist(text) == TaskProgress(done=2, total=3)

    def test_table_form_falls_back_to_last_column_when_no_status_header(self):
        text = (
            "| # | Task | State |\n"
            "|---|------|-------|\n"
            "| 1 | A | done |\n"
            "| 2 | B | todo |\n"
        )
        assert parse_task_checklist(text) == TaskProgress(done=1, total=2)

    def test_separator_rows_ignored(self):
        text = "| # | Status |\n|---|--------|\n| 1 | done |\n|:-:|:-:|\n| 2 | done |\n"
        assert parse_task_checklist(text) == TaskProgress(done=2, total=2)

    def test_legacy_checkbox_form_returns_zero(self):
        text = "- [x] Task one\n- [ ] Task two\n- [X] Task three\n"
        assert parse_task_checklist(text) == TaskProgress(done=0, total=0)

    def test_done_match_is_case_insensitive(self):
        text = (
            "| # | Status |\n|---|--------|\n| 1 | DONE |\n| 2 | Done |\n| 3 | done |\n"
        )
        assert parse_task_checklist(text) == TaskProgress(done=3, total=3)

    def test_blank_status_cells_skipped(self):
        text = (
            "| # | Status |\n"
            "|---|--------|\n"
            "| 1 | done |\n"
            "| 2 |       |\n"
            "| 3 | todo |\n"
        )
        assert parse_task_checklist(text) == TaskProgress(done=1, total=2)
