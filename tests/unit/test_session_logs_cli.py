"""Tests for `tripwire session logs <id>` + `cleanup --with-logs` (H5)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _seed_log(log_dir: Path, session_id: str, timestamp: str, body: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{session_id}-{timestamp}.log"
    path.write_text(body, encoding="utf-8")
    return path


class TestSessionLogs:
    def test_logs_lists_multiple_files(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        log_dir = tmp_path / "logs" / "tmp"
        newer = _seed_log(log_dir, "s1", "20260423T120000", "newer\n")
        _seed_log(log_dir, "s1", "20260423T100000", "older\n")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={
                "claude_session_id": "uuid-1",
                "log_path": str(newer),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "logs",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--list",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "s1-20260423T100000.log" in result.output
        assert "s1-20260423T120000.log" in result.output

    def test_logs_tail_default(self, tmp_path, tmp_path_project, save_test_session):
        log_dir = tmp_path / "logs" / "tmp"
        lines = "\n".join(f"line-{i}" for i in range(1, 101))
        latest = _seed_log(log_dir, "s1", "20260423T120000", lines + "\n")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={
                "claude_session_id": "uuid-1",
                "log_path": str(latest),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "logs",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--tail",
                "50",
            ],
        )

        assert result.exit_code == 0, result.output
        out_lines = result.output.strip().splitlines()
        assert len(out_lines) == 50
        assert out_lines[0] == "line-51"
        assert out_lines[-1] == "line-100"

    def test_logs_full_dumps_everything(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        log_dir = tmp_path / "logs" / "tmp"
        body = "\n".join(f"line-{i}" for i in range(1, 11)) + "\n"
        latest = _seed_log(log_dir, "s1", "20260423T120000", body)

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={
                "claude_session_id": "uuid-1",
                "log_path": str(latest),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["logs", "s1", "--project-dir", str(tmp_path_project), "--full"],
        )

        assert result.exit_code == 0, result.output
        out_lines = result.output.strip().splitlines()
        assert len(out_lines) == 10
        assert out_lines[0] == "line-1"

    def test_logs_errors_when_never_spawned(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="queued")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["logs", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "no recorded log_path" in result.output


class TestCleanupWithLogs:
    def test_cleanup_with_logs_removes_session_log_files(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """cleanup --with-logs must remove the session's log files.
        Other sessions' logs in the same project directory must survive."""
        log_dir = tmp_path / "logs" / "tmp"
        s1_log = _seed_log(log_dir, "s1", "20260423T120000", "s1 body")
        other_log = _seed_log(
            log_dir, "s2", "20260423T120000", "s2 body — must survive"
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            runtime_state={
                "claude_session_id": "uuid-1",
                "log_path": str(s1_log),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "cleanup",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--with-logs",
            ],
        )

        assert result.exit_code == 0, result.output
        assert not s1_log.exists()
        assert other_log.exists()
        assert other_log.read_text() == "s2 body — must survive"

    def test_cleanup_without_logs_preserves_log_files(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        log_dir = tmp_path / "logs" / "tmp"
        s1_log = _seed_log(log_dir, "s1", "20260423T120000", "keep me")

        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            runtime_state={
                "claude_session_id": "uuid-1",
                "log_path": str(s1_log),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert s1_log.exists()
        assert s1_log.read_text() == "keep me"


class TestSessionSummary:
    def test_summary_text_format(self, tmp_path, tmp_path_project, save_test_session):
        """Smoke: the CLI wires session_log_parser and renders the
        expected shape for the happy-path fixture."""
        import shutil

        fixture = (
            Path(__file__).parent.parent / "fixtures" / "stream-json" / "happy_path.log"
        )
        log_dir = tmp_path / "logs" / "tmp"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "s1-20260423T120000.log"
        shutil.copy(fixture, log_file)

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={
                "claude_session_id": "uuid-happy",
                "log_path": str(log_file),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["summary", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert "uuid-happy" in result.output
        assert "success" in result.output
        assert "PR opened" in result.output

    def test_summary_json_format(self, tmp_path, tmp_path_project, save_test_session):
        import json as _json
        import shutil

        fixture = (
            Path(__file__).parent.parent
            / "fixtures"
            / "stream-json"
            / "stop_and_ask.log"
        )
        log_dir = tmp_path / "logs" / "tmp"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "s1-20260423T120000.log"
        shutil.copy(fixture, log_file)

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={
                "claude_session_id": "uuid-ask",
                "log_path": str(log_file),
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "summary",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = _json.loads(result.output)
        assert payload["claude_session_id"] == "uuid-ask"
        assert payload["stopped_to_ask"] is True
        assert payload["exit_subtype"] == "success"
