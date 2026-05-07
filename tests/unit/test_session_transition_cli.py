"""`tripwire session transition <sid> <to>` — explicit status flip.

This is the agent-side replacement for "PM hand-edits session.yaml after
the agent exits". The new exit-protocol step in spawn/defaults.yaml runs
this command to flip `executing → in_review` once the PR is open and
self-reviewed; PM review then runs `complete` (which requires
`in_review`/`verified`).

The command is strict on transitions: arbitrary state jumps are
rejected, so agents can't accidentally skip review.

v0.12: transition is also the validate gate. After writing the new
status (and optionally sweeping issues), the CLI runs `tripwire
validate` and rolls back atomically if any error fires. On transitions
to `in_review`, the PT worktree is also rebased onto `origin/main`.
The `--no-validate` flag bypasses both checks (used in this test
suite's mechanic tests, since the bare fixture project doesn't carry
the artifacts a strict gate would demand).
"""

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


class TestSessionTransition:
    """Mechanic tests — exercise transition state-machine without the
    v0.12 validate gate. Use `--no-validate` so they don't depend on
    the fixture having a complete artifact set."""

    def test_executing_to_in_review_succeeds(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
                "--no-validate",
            ],
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "in_review"

    def test_in_review_to_verified_succeeds(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "verified",
                "--project-dir",
                str(tmp_path_project),
                "--no-validate",
            ],
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

    def test_paused_to_executing_succeeds(self, tmp_path_project, save_test_session):
        """Resume after a pause is the canonical paused→executing flip."""
        save_test_session(tmp_path_project, "s1", status="paused")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "executing",
                "--project-dir",
                str(tmp_path_project),
                "--no-validate",
            ],
        )
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "s1").status == "executing"

    def test_updated_at_advances(self, tmp_path_project, save_test_session):
        from datetime import datetime, timedelta, timezone

        old = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        save_test_session(tmp_path_project, "s1", status="executing", updated_at=old)
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
                "--no-validate",
            ],
        )
        assert result.exit_code == 0, result.output
        after = load_session(tmp_path_project, "s1").updated_at
        assert after > old


class TestAtomicValidateGate:
    """v0.12: transition runs validate post-write and rolls back the
    entire transition (status flip + issue sweeps) if validate errors."""

    def test_validate_failure_rolls_back_status(
        self, tmp_path_project, save_test_session
    ):
        """A failing validate aborts the transition and restores the
        prior session status. Bare project has plan.md as required at
        planning, so transitioning a session with no plan.md → in_review
        triggers `artifact/missing` and rolls back."""
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        # Transition aborted with non-zero exit and clear error.
        assert result.exit_code != 0
        assert "aborted by validate" in result.output
        assert "artifact/missing" in result.output
        # Session status MUST be restored.
        assert load_session(tmp_path_project, "s1").status == "executing"

    def test_validate_failure_rolls_back_swept_issues(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """When sweep advances issues alongside the transition, a
        failing validate must restore both the session AND the issues."""
        from tripwire.core.store import load_issue

        save_test_issue(tmp_path_project, "TMP-1", status="executing")
        save_test_session(tmp_path_project, "s1", status="executing", issues=["TMP-1"])

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        # Both session and issue should be back at executing.
        assert load_session(tmp_path_project, "s1").status == "executing"
        assert load_issue(tmp_path_project, "TMP-1").status == "executing"

    def test_no_validate_flag_bypasses_gate(self, tmp_path_project, save_test_session):
        """--no-validate skips the gate entirely; transition succeeds
        even when validate would fail."""
        save_test_session(tmp_path_project, "s1", status="executing")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "in_review",
                "--project-dir",
                str(tmp_path_project),
                "--no-validate",
            ],
        )
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "s1").status == "in_review"
