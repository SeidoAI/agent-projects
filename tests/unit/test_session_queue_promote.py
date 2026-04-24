"""Tests for I3 — `tripwire session queue --promote-issues`.

A fresh session's issues ship in `backlog` status by default. Before
I3 the PM had to hand-edit each issue's YAML to flip them to `todo`
(no CLI command existed). `--promote-issues` batch-flips every
session issue whose status is `backlog` to `todo`, leaving other
statuses alone.

Readiness also gains a warning-severity item per backlog issue so
that `tripwire session check` surfaces the situation with the
promote hint.
"""

from __future__ import annotations

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_readiness import check_readiness
from tripwire.core.store import load_issue


class TestPromoteIssuesFlag:
    def test_promote_flips_backlog_to_todo_and_queues(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        write_handoff_yaml(tmp_path_project, "s1")
        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_issue(tmp_path_project, "TMP-2", status="backlog")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1", "TMP-2"],
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "queue",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--promote-issues",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "TMP-1: backlog → todo" in result.output
        assert "TMP-2: backlog → todo" in result.output
        assert load_issue(tmp_path_project, "TMP-1").status == "todo"
        assert load_issue(tmp_path_project, "TMP-2").status == "todo"

    def test_promote_ignores_non_backlog(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        """Only `backlog` issues flip. in_progress / todo / done stay put."""
        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_issue(tmp_path_project, "TMP-2", status="in_progress")
        save_test_issue(tmp_path_project, "TMP-3", status="done")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1", "TMP-2", "TMP-3"],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "queue",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--promote-issues",
            ],
        )

        assert result.exit_code == 0, result.output
        assert load_issue(tmp_path_project, "TMP-1").status == "todo"
        assert load_issue(tmp_path_project, "TMP-2").status == "in_progress"
        assert load_issue(tmp_path_project, "TMP-3").status == "done"

    def test_queue_without_flag_leaves_issues_alone(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        """Regression — plain `queue` doesn't touch issue status."""
        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1"],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["queue", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert load_issue(tmp_path_project, "TMP-1").status == "backlog"

    def test_promote_with_no_backlog_issues_is_noop(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        save_test_issue(tmp_path_project, "TMP-1", status="in_progress")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1"],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "queue",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--promote-issues",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "no issues in backlog to promote" in result.output


class TestReadinessBacklogWarning:
    def test_readiness_warns_on_backlog_issue(
        self, tmp_path_project, save_test_session, save_test_issue, write_handoff_yaml
    ):
        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1"],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        report = check_readiness(tmp_path_project, "s1")

        backlog_items = [i for i in report.items if "status=backlog" in i.label]
        assert len(backlog_items) == 1
        assert backlog_items[0].severity == "warning"
        assert "--promote-issues" in (backlog_items[0].fix_hint or "")
        # Warning-severity items don't block readiness (ready=True even
        # though the backlog item is `passing=False` — ready tracks only
        # error severities).
        assert report.ready is True

    def test_readiness_quiet_when_issues_are_todo(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        save_test_issue(tmp_path_project, "TMP-1", status="todo")
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="planned",
            issues=["TMP-1"],
        )
        report = check_readiness(tmp_path_project, "s1")
        assert not any("status=backlog" in i.label for i in report.items)
