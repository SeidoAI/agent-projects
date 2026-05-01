"""Tests for `tripwire tripwires list` — PM-side registry inspection."""

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
    """Set the PM role marker so the command is reachable."""
    role_dir = tmp_path / "tripwire_home"
    role_dir.mkdir()
    (role_dir / "role").write_text("pm", encoding="utf-8")
    monkeypatch.setenv("TRIPWIRE_HOME", str(role_dir))
    return role_dir


def test_tripwires_list_lists_registered_tripwires(
    tmp_path: Path, pm_role: Path
) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["tripwires", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "self-review" in result.output
    assert "session.complete" in result.output
    # Without --reveal the prompt body is hidden.
    assert "AC met but not really" not in result.output


def test_tripwires_list_reveal_shows_prompt(tmp_path: Path, pm_role: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "tripwires",
            "list",
            "--project-dir",
            str(tmp_path),
            "--reveal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "self-review" in result.output
    assert "--ack" in result.output


def test_tripwires_list_disabled_project_says_disabled(
    tmp_path: Path, pm_role: Path
) -> None:
    _project(tmp_path, {"enabled": False})
    runner = CliRunner()
    result = runner.invoke(cli, ["tripwires", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (
        "disabled" in result.output.lower() or "no tripwires" in result.output.lower()
    )


def test_tripwires_list_requires_pm_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path)
    role_dir = tmp_path / "tripwire_home"
    role_dir.mkdir()
    # No role file means executor mode → command refuses.
    monkeypatch.setenv("TRIPWIRE_HOME", str(role_dir))
    monkeypatch.delenv("TRIPWIRE_ROLE", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["tripwires", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "pm" in result.output.lower() or "role" in result.output.lower()


def test_tripwires_list_role_via_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TRIPWIRE_ROLE=pm` env var is the alternate role gate."""
    _project(tmp_path)
    monkeypatch.setenv("TRIPWIRE_ROLE", "pm")
    # Avoid bleed-through from prior fixtures.
    monkeypatch.delenv("TRIPWIRE_HOME", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["tripwires", "list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
