"""``tripwire session batch-spawn`` CLI (KUI-96 §E3)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def test_batch_spawn_runs_priming_and_each_spawn(
    save_test_session, tmp_path_project: Path, monkeypatch
) -> None:
    """``batch-spawn s1 s2`` triggers priming + each session's spawn."""
    save_test_session(tmp_path_project, session_id="s1")
    save_test_session(tmp_path_project, session_id="s2")

    calls: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append("prime")
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append(f"spawn:{session_id}")

    from tripwire.core import batch_spawn as bs

    monkeypatch.setattr(bs, "default_prime_runner", fake_prime)
    monkeypatch.setattr(bs, "default_spawn_runner", fake_spawn)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "batch-spawn",
            "s1",
            "s2",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == ["prime", "spawn:s1", "spawn:s2"]


def test_batch_spawn_no_prime_flag(
    save_test_session, tmp_path_project: Path, monkeypatch
) -> None:
    """``--no-prime`` skips the priming call."""
    save_test_session(tmp_path_project, session_id="s1")
    save_test_session(tmp_path_project, session_id="s2")

    calls: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append("prime")
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append(f"spawn:{session_id}")

    from tripwire.core import batch_spawn as bs

    monkeypatch.setattr(bs, "default_prime_runner", fake_prime)
    monkeypatch.setattr(bs, "default_spawn_runner", fake_spawn)

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "batch-spawn",
            "--no-prime",
            "s1",
            "s2",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == ["spawn:s1", "spawn:s2"]


def test_batch_spawn_requires_at_least_one_session(tmp_path_project: Path) -> None:
    """No session id args → click error."""
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["batch-spawn", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code != 0
