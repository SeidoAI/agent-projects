"""Tests for the `--profile` flag added by `@profileable`.

Verifies the behaviour of the decorator on `validate`:
  - No flag → no profile file written, command runs normally
  - `--profile` (no value) → writes to `.tripwire.profile`
  - `--profile=PATH` → writes to PATH
  - The profile file is non-empty and parseable with `pstats.Stats`
"""

from __future__ import annotations

import os
import pstats
from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli._profiling import DEFAULT_PROFILE_PATH
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


def test_no_profile_flag_creates_no_file(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    _init(runner, target)

    cwd_before = set(Path.cwd().iterdir())
    result = runner.invoke(
        cli,
        ["validate", "--project-dir", str(target)],
    )
    assert result.exit_code == 0, result.output

    cwd_after = set(Path.cwd().iterdir())
    new = cwd_after - cwd_before
    assert not any(p.name == DEFAULT_PROFILE_PATH for p in new), (
        f"Expected no profile file, found: {new}"
    )


def test_profile_flag_writes_to_explicit_path(
    runner: CliRunner, tmp_path: Path
) -> None:
    target = tmp_path / "p"
    _init(runner, target)

    profile_path = tmp_path / "out.prof"
    result = runner.invoke(
        cli,
        [
            "validate",
            "--project-dir",
            str(target),
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert profile_path.exists(), result.output
    assert profile_path.stat().st_size > 0


def test_profile_flag_writes_to_default_path(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--profile` with no value uses the DEFAULT_PROFILE_PATH (in cwd)."""
    target = tmp_path / "p"
    _init(runner, target)

    # Run from a temp cwd so the default file doesn't pollute the repo.
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    result = runner.invoke(
        cli,
        ["validate", "--project-dir", str(target), "--profile"],
    )
    assert result.exit_code == 0, result.output
    expected = work_dir / DEFAULT_PROFILE_PATH
    assert expected.exists(), os.listdir(work_dir)
    assert expected.stat().st_size > 0


def test_profile_file_parses_with_pstats(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "p"
    _init(runner, target)

    profile_path = tmp_path / "out.prof"
    result = runner.invoke(
        cli,
        [
            "validate",
            "--project-dir",
            str(target),
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0

    # Should parse as a valid cProfile dump and contain stats records.
    stats = pstats.Stats(str(profile_path))
    assert stats.total_calls > 0
    assert stats.total_tt > 0
