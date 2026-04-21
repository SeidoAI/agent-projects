"""Concurrent `tripwire validate --fix` integration test.

The most important safety property of `apply_fixes` is that two concurrent
`tripwire validate --fix` invocations can't overwrite each other. This test
fires 5 parallel subprocesses at a project that has multiple fixable
issues and confirms every fix landed (no lost writes).

Mirrors the pattern in `test_next_key.py::TestConcurrentSubprocess` but
exercises the validator's auto-fix path instead of the key allocator.
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
from tripwire.core.parser import parse_frontmatter_body


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_project(runner: CliRunner, target: Path) -> None:
    result = runner.invoke(
        cli,
        [
            "init",
            str(target),
            "--name",
            "concurrent-fix-test",
            "--key-prefix",
            "TST",
            "--base-branch",
            "main",
            "--non-interactive",
            "--no-git",
        ],
    )
    assert result.exit_code == 0, result.output


def _write_issue_without_uuid(project_dir: Path, n: int) -> None:
    """Write a minimal issue YAML that's missing a uuid — the easiest
    fixable defect to seed many instances of."""
    body = (
        "## Context\n[[anchor-node]]\n\n## Implements\nREQ\n\n"
        "## Repo scope\nbackend\n\n## Requirements\n- thing\n\n"
        "## Execution constraints\nIf ambiguous, stop and ask.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n## Definition of Done\n- [ ] done\n"
    )
    text = (
        "---\n"
        f"id: TST-{n}\n"
        f"title: Concurrent-fix test {n}\n"
        "status: todo\n"
        "priority: medium\n"
        "executor: ai\n"
        "verifier: required\n"
        "created_at: '2026-04-07T10:00:00'\n"
        "updated_at: '2026-04-07T10:00:00'\n"
        "---\n" + body
    )
    idir = project_dir / "issues" / f"TST-{n}"
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "issue.yaml").write_text(text, encoding="utf-8")


def _seed_anchor_node(project_dir: Path) -> None:
    """The issues reference `[[anchor-node]]` — create it so
    ref/dangling doesn't drown out the uuid/missing fixes."""
    (project_dir / "nodes").mkdir(parents=True, exist_ok=True)
    (project_dir / "nodes" / "anchor-node.yaml").write_text(
        "---\n"
        "uuid: 11111111-1111-4111-8111-111111111111\n"
        "id: anchor-node\n"
        "type: model\n"
        "name: Anchor\n"
        "status: active\n"
        "created_at: '2026-04-07T10:00:00'\n"
        "updated_at: '2026-04-07T10:00:00'\n"
        "---\n"
        "Shared anchor.\n",
        encoding="utf-8",
    )


def _run_fix(project_dir_str: str) -> int:
    """Run `tripwire validate --fix` via subprocess.

    Returns the exit code. We don't care about stdout — we'll inspect
    the files afterwards.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tripwire.cli.main",
            "validate",
            "--fix",
            "--project-dir",
            project_dir_str,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def _read_frontmatter(path: Path) -> dict:
    fm, _ = parse_frontmatter_body(path.read_text(encoding="utf-8"))
    return fm


class TestConcurrentFix:
    def test_five_concurrent_fix_processes_no_lost_writes(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Seed 10 issues with missing UUIDs. Fire 5 concurrent
        `tripwire validate --fix` processes. Every issue must end up with a
        valid UUID — none can be lost to a race between writers."""
        target = tmp_path / "p"
        _init_project(runner, target)
        _seed_anchor_node(target)
        for n in range(1, 11):
            _write_issue_without_uuid(target, n)

        with ProcessPoolExecutor(max_workers=5) as ex:
            list(ex.map(_run_fix, [str(target)] * 5))

        # Every issue file now has a uuid.
        for n in range(1, 11):
            fm = _read_frontmatter(target / "issues" / f"TST-{n}" / "issue.yaml")
            assert "uuid" in fm, f"TST-{n} missing uuid after concurrent --fix"
            uid = str(fm["uuid"]).replace("-", "")
            assert len(uid) == 32, f"TST-{n} uuid has wrong shape: {fm['uuid']}"

        # And project.yaml sequence drift converged to the right value.
        raw = yaml.safe_load((target / "project.yaml").read_text())
        assert raw["next_issue_number"] == 11, raw["next_issue_number"]
