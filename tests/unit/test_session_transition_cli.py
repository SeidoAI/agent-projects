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
    """v0.13: transition gates are scoped to the route's
    ``controls.tripwires``, not full ``validate_project``. Full project
    validation is now a separate command (``tripwire validate``). The
    bare-project assumptions of these v0.12-era tests no longer apply
    — see ``tests/unit/core/test_transitions_executor.py`` for the
    v0.13 atomic-rollback contract.

    Two tests removed in v0.13:
    - ``test_validate_failure_rolls_back_status`` (bare project no longer
      auto-fails the transition)
    - ``test_validate_failure_rolls_back_swept_issues`` (same)
    """

    def test_no_validate_flag_is_accepted_for_bw_compat(
        self, tmp_path_project, save_test_session
    ):
        """``--no-validate`` is preserved for backwards compatibility but
        is now a no-op; v0.13 gate is route-scoped, not project-wide."""
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
