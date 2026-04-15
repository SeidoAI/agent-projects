"""keel session CLI (v0.6a additions: derive-branch, check, progress)."""

from click.testing import CliRunner

from keel.cli.session import session_cmd


class TestDeriveBranch:
    def test_derive_branch_happy(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        """derive-branch reads primary issue kind and emits <kind>/<slug>."""
        save_test_issue(
            tmp_path_project, key="TMP-1", kind="feat", title="Setup Infra"
        )
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
