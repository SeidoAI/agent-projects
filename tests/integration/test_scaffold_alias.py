"""Tests for the `brief` command and its hidden `scaffold-for-creation` alias.

`brief` is the user-facing name (as of the v0 finalization). The old
`scaffold-for-creation` stays registered as a hidden alias for backward
compatibility so any scripts or skill files that still reference the old
name keep working. Both commands must produce identical output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init(runner: CliRunner, target: Path) -> None:
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "test",
            "--key-prefix",
            "TST",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0, result.output


def test_brief_command_works(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    _init(runner, target)
    result = runner.invoke(cli, ["brief", "--project-dir", str(target)])
    assert result.exit_code == 0, result.output
    assert "PROJECT:" in result.output
    assert "NEXT IDS:" in result.output
    assert "VALIDATION GATE" in result.output


def test_scaffold_for_creation_alias_still_works(
    runner: CliRunner, tmp_path: Path
) -> None:
    target = tmp_path / "p"
    _init(runner, target)
    result = runner.invoke(cli, ["scaffold-for-creation", "--project-dir", str(target)])
    assert result.exit_code == 0, result.output
    assert "PROJECT:" in result.output


def test_brief_and_alias_produce_identical_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    target = tmp_path / "p"
    _init(runner, target)

    brief_result = runner.invoke(cli, ["brief", "--project-dir", str(target)])
    alias_result = runner.invoke(
        cli, ["scaffold-for-creation", "--project-dir", str(target)]
    )

    assert brief_result.exit_code == 0
    assert alias_result.exit_code == 0
    assert brief_result.output == alias_result.output


def test_scaffold_alias_hidden_from_help(runner: CliRunner) -> None:
    """The `scaffold-for-creation` alias should not appear in `tripwire --help`."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "brief" in result.output
    assert "scaffold-for-creation" not in result.output


def test_brief_in_help(runner: CliRunner) -> None:
    """`brief` should appear in `tripwire --help` with its description."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "brief" in result.output
