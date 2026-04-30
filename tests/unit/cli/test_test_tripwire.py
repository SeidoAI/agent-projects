"""KUI-136 (B2) — `tripwire test-tripwire <id>` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


def _project(tmp_path: Path, tripwires: dict | None = None) -> None:
    body: dict = {
        "name": "fixture",
        "key_prefix": "FIX",
        "base_branch": "main",
        "next_issue_number": 1,
        "next_session_number": 1,
        "phase": "scoping",
    }
    if tripwires is not None:
        body["tripwires"] = tripwires
    (tmp_path / "project.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


@pytest.fixture
def pm_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    role_dir = tmp_path / "tripwire_home"
    role_dir.mkdir()
    (role_dir / "role").write_text("pm", encoding="utf-8")
    monkeypatch.setenv("TRIPWIRE_HOME", str(role_dir))
    return role_dir


def test_test_tripwire_prints_prompt(tmp_path: Path, pm_role: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["test-tripwire", "self-review", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    # The self-review prompt mentions --ack regardless of variation.
    assert "--ack" in result.output


def test_test_tripwire_unknown_id_exits_nonzero(
    tmp_path: Path, pm_role: Path
) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["test-tripwire", "no-such-tripwire", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
    # Surfaces the registry contents so the author sees what IS available.
    assert "self-review" in result.output


def test_test_tripwire_session_overrides_variation_seed(
    tmp_path: Path, pm_role: Path
) -> None:
    """Different --session ids must produce a deterministic prompt each."""
    _project(tmp_path)
    runner = CliRunner()
    a = runner.invoke(
        cli,
        [
            "test-tripwire",
            "self-review",
            "--session",
            "seed-a",
            "--project-dir",
            str(tmp_path),
        ],
    )
    b = runner.invoke(
        cli,
        [
            "test-tripwire",
            "self-review",
            "--session",
            "seed-a",
            "--project-dir",
            str(tmp_path),
        ],
    )
    # Same session id → same prompt.
    assert a.exit_code == 0 and b.exit_code == 0
    assert a.output == b.output


def test_test_tripwire_ack_writes_marker(tmp_path: Path, pm_role: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "test-tripwire",
            "self-review",
            "--session",
            "sess-1",
            "--ack",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    marker = tmp_path / ".tripwire" / "acks" / "self-review-sess-1.json"
    assert marker.is_file()


def test_test_tripwire_requires_pm_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path)
    role_dir = tmp_path / "tripwire_home"
    role_dir.mkdir()
    monkeypatch.setenv("TRIPWIRE_HOME", str(role_dir))
    monkeypatch.delenv("TRIPWIRE_ROLE", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["test-tripwire", "self-review", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "pm" in result.output.lower() or "role" in result.output.lower()
