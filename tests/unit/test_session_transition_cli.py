"""`tripwire session transition <sid> <to>` — explicit status flip.

This is the agent-side replacement for "PM hand-edits session.yaml after
the agent exits". The new exit-protocol step in spawn/defaults.yaml runs
this command to flip `executing → in_review` once the PR is open and
self-reviewed; PM review then runs `complete` (which requires
`in_review`/`verified`).

The command is strict on transitions: arbitrary state jumps are
rejected, so agents can't accidentally skip review.
"""

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


class TestSessionTransition:
    def test_executing_to_in_review_succeeds(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "in_review", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "in_review"

    def test_in_review_to_verified_succeeds(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="in_review")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "verified", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "s1").status == "verified"

    def test_invalid_target_rejected(self, tmp_path_project, save_test_session):
        """`executing → done` must NOT be allowed — agents have to go
        through review first."""
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "done", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert load_session(tmp_path_project, "s1").status == "executing"

    def test_unknown_status_rejected(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "bogus", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert load_session(tmp_path_project, "s1").status == "executing"

    def test_missing_session_rejected(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "nonexistent",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0

    def test_paused_to_executing_succeeds(
        self, tmp_path_project, save_test_session
    ):
        """Resume after a pause is the canonical paused→executing flip."""
        save_test_session(tmp_path_project, "s1", status="paused")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "executing", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "s1").status == "executing"

    def test_updated_at_advances(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="executing")
        before = load_session(tmp_path_project, "s1").updated_at
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["transition", "s1", "in_review", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        after = load_session(tmp_path_project, "s1").updated_at
        assert after > before
