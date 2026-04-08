"""Tests for the root `-v/--verbose` flag.

The flag is a Click count option on the root group. It maps to:
  default → WARNING
  -v → INFO
  -vv → DEBUG

Configuration is done via `logging.basicConfig(force=True)` so the change
applies even inside `CliRunner` test invocations.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_project.cli.main import LOG_LEVELS, cli


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


def test_log_levels_constant_maps_count_to_level() -> None:
    """The mapping is the public contract — verify it explicitly."""
    assert LOG_LEVELS[0] == logging.WARNING
    assert LOG_LEVELS[1] == logging.INFO
    assert LOG_LEVELS[2] == logging.DEBUG


def test_no_flag_sets_warning_level(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "x",
            "--key-prefix",
            "X",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0
    # No verbose flag → root logger should not be at INFO/DEBUG
    assert logging.getLogger().level >= logging.WARNING


def test_v_sets_info_level(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    _init(runner, target)
    result = runner.invoke(
        cli,
        ["-v", "validate", "--project-dir", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.INFO


def test_vv_sets_debug_level(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    _init(runner, target)
    result = runner.invoke(
        cli,
        ["-vv", "validate", "--project-dir", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.DEBUG


def test_verbose_validate_emits_info_logs(
    runner: CliRunner, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """At INFO level, validate should announce its start and completion."""
    target = tmp_path / "p"
    _init(runner, target)

    with caplog.at_level(logging.INFO, logger="agent_project.core.validator"):
        result = runner.invoke(
            cli,
            ["-v", "validate", "--project-dir", str(target)],
        )
    assert result.exit_code == 0, result.output

    messages = [r.getMessage() for r in caplog.records]
    assert any("validate_project: starting" in m for m in messages), messages
    assert any("validate_project: complete" in m for m in messages), messages


def test_verbose_validate_emits_debug_logs(
    runner: CliRunner, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """At DEBUG level, individual checks should be timed and reported."""
    target = tmp_path / "p"
    _init(runner, target)

    with caplog.at_level(logging.DEBUG, logger="agent_project.core.validator"):
        result = runner.invoke(
            cli,
            ["-vv", "validate", "--project-dir", str(target)],
        )
    assert result.exit_code == 0, result.output

    messages = [r.getMessage() for r in caplog.records]
    # Each check is logged with its function name and a duration in ms.
    assert any("check_uuid_present" in m for m in messages), messages
