"""Integration tests for `tripwire next-key`.

The single most important test in this file is the concurrent-subprocess
case: fire 10 parallel CLI invocations at the same project and confirm
they produce 10 distinct sequential keys with no gaps or collisions. The
core allocator is already unit-tested for this via threads + processes
in `test_key_allocator.py`; this test exercises the end-to-end path
through the Click command and the real `tripwire` entry point.
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_project(
    runner: CliRunner,
    target: Path,
    key_prefix: str = "TST",
) -> None:
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "t",
            "--key-prefix",
            key_prefix,
            "--base-branch",
            "main",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0, result.output


# ============================================================================
# Basic invocation
# ============================================================================


class TestBasic:
    def test_single_issue_key(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        assert result.exit_code == 0
        assert result.output.strip() == "TST-1"

    def test_sequential_invocations(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        first = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        second = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        third = runner.invoke(cli, ["next-key", "--project-dir", str(target)])

        assert first.output.strip() == "TST-1"
        assert second.output.strip() == "TST-2"
        assert third.output.strip() == "TST-3"

    def test_batch_allocation(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        result = runner.invoke(
            cli, ["next-key", "--project-dir", str(target), "--count", "5"]
        )
        assert result.exit_code == 0
        keys = result.output.strip().split("\n")
        assert keys == ["TST-1", "TST-2", "TST-3", "TST-4", "TST-5"]

    def test_batch_then_single_advances_counter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        runner.invoke(cli, ["next-key", "--project-dir", str(target), "--count", "3"])
        single = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        assert single.output.strip() == "TST-4"

    def test_counter_persisted_to_project_yaml(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        runner.invoke(cli, ["next-key", "--project-dir", str(target), "--count", "5"])
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["next_issue_number"] == 6

    def test_session_type_uses_different_counter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        # Allocate a couple of issue keys to advance the issue counter.
        runner.invoke(cli, ["next-key", "--project-dir", str(target), "--count", "3"])
        # Session counter should still start from 1.
        result = runner.invoke(
            cli, ["next-key", "--project-dir", str(target), "--type", "session"]
        )
        assert result.exit_code == 0
        # Session keys use the `<PREFIX>-S<N>` form from core.key_allocator
        assert result.output.strip() == "TST-S1"

    def test_uses_configured_key_prefix(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target, key_prefix="PKB")
        result = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        assert result.output.strip() == "PKB-1"


# ============================================================================
# Error handling
# ============================================================================


class TestErrors:
    def test_missing_project_yaml(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["next-key", "--project-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "project.yaml not found" in result.output

    def test_invalid_type_rejected_by_click(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["next-key", "--project-dir", str(target), "--type", "bogus"]
        )
        assert result.exit_code != 0

    def test_zero_count_rejected_by_click(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["next-key", "--project-dir", str(target), "--count", "0"]
        )
        assert result.exit_code != 0

    def test_negative_count_rejected_by_click(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)
        result = runner.invoke(
            cli, ["next-key", "--project-dir", str(target), "--count", "-3"]
        )
        assert result.exit_code != 0


# ============================================================================
# Concurrent subprocess — the critical correctness test
# ============================================================================


def _allocate_via_subprocess(project_dir_str: str) -> str:
    """Top-level function for ProcessPoolExecutor (must be pickleable).

    Shells out to the real `tripwire` entry point so we exercise the
    wheel-installed script path, not just the in-process Click runner.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tripwire.cli.main",
            "next-key",
            "--project-dir",
            project_dir_str,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"next-key subprocess failed: rc={result.returncode} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result.stdout.strip()


class TestConcurrentSubprocess:
    def test_ten_concurrent_subprocesses_no_collisions(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """10 concurrent subprocesses must produce 10 distinct keys.

        This is the end-to-end version of the concurrent test in
        `test_key_allocator.py::test_concurrent_processes_no_collisions`.
        That test hits `allocate_keys()` directly; this one goes through
        Click + argv parsing + the `tripwire` script shim. If the
        file lock fails at any layer, this test will produce duplicates.
        """
        target = tmp_path / "p"
        _init_project(runner, target)

        with ProcessPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(_allocate_via_subprocess, [str(target)] * 10))

        assert len(results) == 10
        assert len(set(results)) == 10, (
            f"Duplicate keys produced under concurrency: {sorted(results)}"
        )
        expected = {f"TST-{i}" for i in range(1, 11)}
        assert set(results) == expected

        # And the counter should be exactly at 11 after all 10 allocations.
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["next_issue_number"] == 11


# ============================================================================
# Works after brief
# ============================================================================


class TestScaffoldIntegration:
    def test_scaffold_shows_next_key_matching_what_allocator_returns(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "p"
        _init_project(runner, target)

        scaffold = runner.invoke(cli, ["brief", "--project-dir", str(target)])
        assert "next issue key: TST-1" in scaffold.output

        allocated = runner.invoke(cli, ["next-key", "--project-dir", str(target)])
        assert allocated.output.strip() == "TST-1"

        # After allocation, scaffold should advance
        scaffold_after = runner.invoke(cli, ["brief", "--project-dir", str(target)])
        assert "next issue key: TST-2" in scaffold_after.output
