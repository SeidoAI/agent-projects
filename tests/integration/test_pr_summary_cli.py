"""End-to-end tests for ``tripwire pr-summary``.

The CLI is a thin wrapper around the compute + renderer modules — these
tests verify the wiring (Click registration, default refs, project-dir
flag, format switch) and the marker line on stdout, which CI uses as
the comment discriminator.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.main import cli
from tripwire.core.pr_summary_renderer import MARKER


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _seed_two_state_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "project.yaml").write_text(
        "name: cli-fixture\n"
        "key_prefix: CLI\n"
        "next_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (repo / sub).mkdir(parents=True, exist_ok=True)
    artifacts = repo / "templates" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "manifest.yaml").write_text("artifacts: []\n", encoding="utf-8")

    from tripwire.core.store import save_issue
    from tripwire.models import Issue

    body = (
        "## Context\nseed.\n\n"
        "## Implements\nREQ\n\n"
        "## Repo scope\n- repo/x\n\n"
        "## Requirements\n- thing\n\n"
        "## Execution constraints\nIf ambiguous, stop.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n"
        "## Definition of Done\n- [ ] done\n"
    )
    save_issue(
        repo,
        Issue.model_validate(
            {
                "id": "CLI-1",
                "title": "First",
                "status": "queued",
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
                "kind": "feat",
                "body": body,
            }
        ),
        update_cache=False,
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    save_issue(
        repo,
        Issue.model_validate(
            {
                "id": "CLI-1",
                "title": "First",
                "status": "completed",
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
                "kind": "feat",
                "body": body,
            }
        ),
        update_cache=False,
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "head")
    head_sha = _git(repo, "rev-parse", "HEAD")

    return repo, base_sha, head_sha


@pytest.fixture
def two_state_repo(tmp_path: Path) -> tuple[Path, str, str]:
    return _seed_two_state_repo(tmp_path)


def test_cli_outputs_marker_first(two_state_repo):
    repo, base_sha, head_sha = two_state_repo
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "pr-summary",
            "--project-dir",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == MARKER


def test_cli_includes_section_summaries(two_state_repo):
    repo, base_sha, head_sha = two_state_repo
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "pr-summary",
            "--project-dir",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
        ],
    )
    assert result.exit_code == 0, result.output
    out = result.output
    for needle in (
        "Validation",
        "Issues",
        "Sessions",
        "Concept graph",
        "Critical path",
        "Workspace sync",
        "Lint",
    ):
        assert needle in out, f"missing section header: {needle}"


def test_cli_surfaces_issue_status_change(two_state_repo):
    repo, base_sha, head_sha = two_state_repo
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "pr-summary",
            "--project-dir",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
        ],
    )
    assert result.exit_code == 0, result.output
    # v0.9.4 canonical names.
    assert "`CLI-1`: queued → completed" in result.output


def test_cli_json_format_returns_parseable_json(two_state_repo):
    repo, base_sha, head_sha = two_state_repo
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "pr-summary",
            "--project-dir",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["base_sha"] == base_sha
    assert data["head_sha"] == head_sha
    assert any(
        c["id"] == "CLI-1"
        and c["from_status"] == "queued"
        and c["to_status"] == "completed"
        for c in data["issues"]["changes"]
    )


def test_cli_errors_outside_git_repo(tmp_path: Path):
    runner = CliRunner()
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    result = runner.invoke(
        cli,
        ["pr-summary", "--project-dir", str(not_a_repo)],
    )
    assert result.exit_code != 0
