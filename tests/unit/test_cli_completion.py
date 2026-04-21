"""Tests for the `tripwire completion <shell>` subcommand.

The subcommand prints install instructions for tab completion in
bash/zsh/fish. Click handles the actual completion via its
`_TRIPWIRE_COMPLETE` env var mechanism — we don't test that here.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tripwire.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_completion_bash_prints_install_snippet(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["completion", "bash"])
    assert result.exit_code == 0, result.output
    assert "_TRIPWIRE_COMPLETE=bash_source" in result.output
    assert "~/.bashrc" in result.output


def test_completion_zsh_prints_install_snippet(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["completion", "zsh"])
    assert result.exit_code == 0, result.output
    assert "_TRIPWIRE_COMPLETE=zsh_source" in result.output
    assert "~/.zshrc" in result.output


def test_completion_fish_prints_install_snippet(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["completion", "fish"])
    assert result.exit_code == 0, result.output
    assert "_TRIPWIRE_COMPLETE=fish_source" in result.output
    assert "~/.config/fish/completions/tripwire.fish" in result.output


def test_completion_unknown_shell_rejected(runner: CliRunner) -> None:
    """Click's Choice() validator rejects shells outside the supported set."""
    result = runner.invoke(cli, ["completion", "elvish"])
    assert result.exit_code != 0
    # Click reports the invalid choice in the error
    assert "elvish" in result.output or "invalid choice" in result.output.lower()
