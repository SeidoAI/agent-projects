"""Tests for tripwire session attach."""

from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


class TestSessionAttach:
    def test_attach_manual_runtime_prints_instruction(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "manual"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt",
                        "branch": "feat/s1",
                    }
                ],
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert "claude --name s1 --session-id uuid-1" in result.output

    def test_attach_tmux_runtime_execs_tmux(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "tmux_session_name": "tw-s1",
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt",
                        "branch": "feat/s1",
                    }
                ],
            },
        )

        with patch("os.execvp") as mock_execvp:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["attach", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        mock_execvp.assert_called_once()
        prog, argv = mock_execvp.call_args[0]
        assert prog == "tmux"
        assert "tw-s1" in argv

    def test_attach_session_not_found(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "nope", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_attach_returns_instruction_when_tmux_name_missing(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={"claude_session_id": "uuid-1"},
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert (
            "no tmux session" in result.output.lower()
            or "not found" in result.output.lower()
        )
