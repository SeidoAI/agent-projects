"""keel session CLI (v0.6a additions: derive-branch, check, progress)."""

from click.testing import CliRunner

from keel.cli.session import session_cmd


class TestDeriveBranch:
    def test_derive_branch_happy(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        """derive-branch reads primary issue kind and emits <kind>/<slug>."""
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="Setup Infra")
        save_test_session(
            tmp_path_project,
            session_id="session-setup-infra",
            issues=["TMP-1"],
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "derive-branch",
                "session-setup-infra",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "feat/setup-infra"

    def test_derive_branch_rejects_unknown_session(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "derive-branch",
                "session-nonexistent",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_derive_branch_rejects_session_with_no_issues(
        self, save_test_session, tmp_path_project
    ):
        save_test_session(
            tmp_path_project,
            session_id="session-empty",
            issues=[],
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "derive-branch",
                "session-empty",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "no issues" in result.output.lower()


class TestSessionCheck:
    def test_session_check_reports_missing_handoff(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="Setup")
        save_test_session(
            tmp_path_project,
            session_id="session-setup",
            issues=["TMP-1"],
            plan=True,
        )
        # No handoff.yaml written yet — check should surface error.

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "check",
                "session-setup",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "handoff.yaml" in result.output.lower()

    def test_session_check_passes_when_ready(
        self,
        save_test_issue,
        save_test_session,
        tmp_path_project,
        write_handoff_yaml,
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="Setup")
        save_test_session(
            tmp_path_project,
            session_id="session-setup",
            issues=["TMP-1"],
            plan=True,
            status="planned",
        )
        write_handoff_yaml(tmp_path_project, "session-setup", branch="feat/setup")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "check",
                "session-setup",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "launch-ready" in result.output.lower()

    def test_session_check_reports_unresolved_blocker(
        self,
        save_test_issue,
        save_test_session,
        tmp_path_project,
        write_handoff_yaml,
    ):
        save_test_issue(
            tmp_path_project, key="TMP-1", kind="feat", title="Blocker", status="todo"
        )
        save_test_issue(
            tmp_path_project,
            key="TMP-2",
            kind="feat",
            title="Blocked",
            blocked_by=["TMP-1"],
        )
        save_test_session(
            tmp_path_project,
            session_id="session-blocked",
            issues=["TMP-2"],
            plan=True,
        )
        write_handoff_yaml(tmp_path_project, "session-blocked", branch="feat/blocked")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "check",
                "session-blocked",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "blocker" in result.output.lower()
        assert "TMP-1" in result.output


class TestSessionProgress:
    def test_progress_aggregates_active_only(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="One")
        save_test_issue(tmp_path_project, key="TMP-2", kind="feat", title="Two")
        save_test_session(
            tmp_path_project,
            session_id="session-one",
            issues=["TMP-1"],
            status="implementing",
        )
        save_test_session(
            tmp_path_project,
            session_id="session-two",
            issues=["TMP-2"],
            status="planned",
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["progress", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert "session-one" in result.output
        assert "session-two" not in result.output

    def test_progress_counts_tasks_from_checklist(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="X")
        save_test_session(
            tmp_path_project,
            session_id="session-x",
            issues=["TMP-1"],
            status="implementing",
        )
        checklist = tmp_path_project / "sessions" / "session-x" / "task-checklist.md"
        checklist.write_text(
            "- [x] one\n- [x] two\n- [ ] three\n- [ ] four\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "progress",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        import json as _json

        payload = _json.loads(result.output)
        assert payload[0]["tasks_total"] == 4
        assert payload[0]["tasks_done"] == 2
