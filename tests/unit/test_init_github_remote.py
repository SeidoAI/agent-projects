"""Tests for `tripwire init`'s v0.7.6 GitHub remote setup (item A).

The init flow's new responsibility: auto-create the project-tracking
GitHub repo, configure ``origin``, and push the initial commit. Three
opt-out flags (``--no-github-repo``, ``--no-remote``, ``--no-push``)
plus a ``--public`` visibility opt-in.

Tests mock both `httpx` (no real network) and ``subprocess.run`` for
git so we never touch the operator's real repos.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli import init as init_module
from tripwire.cli.init import init_cmd
from tripwire.core import github_client


# ============================================================================
# Helpers
# ============================================================================


def _base_args(target: Path) -> list[str]:
    """The minimum non-interactive flag set for an init smoke."""
    return [
        str(target),
        "--non-interactive",
        "--name",
        "demo",
        "--key-prefix",
        "DEM",
        "--base-branch",
        "main",
        "--github-owner",
        "alice",
        "--github-repo",
        "demo-tracking",
    ]


@pytest.fixture
def fake_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture every `subprocess.run` invocation via the init module.

    Returns a list of argv lists, in call order. Each call returns a
    successful CompletedProcess so init flows through to the next step.
    The exception is `git remote get-url origin` which we want to fail
    so the "add remote" branch runs (init has no pre-existing origin).
    """
    calls: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(list(args))
        if args[:4] == ["git", "remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(args, returncode=128, stderr=b"")
        if args[:3] == ["git", "rev-parse", "--verify"]:
            # Pretend HEAD is missing so the initial commit branch runs.
            return subprocess.CompletedProcess(args, returncode=128, stderr=b"")
        return subprocess.CompletedProcess(args, returncode=0, stderr=b"")

    monkeypatch.setattr(init_module.subprocess, "run", _fake_run)
    return calls


@pytest.fixture
def fake_token(monkeypatch: pytest.MonkeyPatch) -> str:
    """Force the token resolver to return a known value."""
    monkeypatch.setattr(github_client, "resolve_token", lambda: "test-token")
    monkeypatch.setattr(
        github_client, "_authenticated_owner", lambda token: "alice"
    )
    return "test-token"


def _argv_summary(calls: list[list[str]]) -> list[str]:
    """Compact "git X Y Z" strings for assertion readability."""
    return [" ".join(c) for c in calls]


# ============================================================================
# Happy path: auto-create + remote + push
# ============================================================================


class TestHappyPath:
    def test_creates_repo_adds_remote_and_pushes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        # GH API: 404 on repo_exists → create_repo returns the SSH URL.
        monkeypatch.setattr(
            github_client, "repo_exists", lambda *_a, **_kw: False
        )
        captured: dict[str, Any] = {}

        def _fake_create(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured["owner"] = owner
            captured["repo"] = repo
            captured["private"] = kwargs.get("private")
            return {"ssh_url": f"git@github.com:{owner}/{repo}.git"}

        monkeypatch.setattr(github_client, "create_repo", _fake_create)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target))

        assert result.exit_code == 0, result.output

        # API was called with the expected (owner, repo, private).
        assert captured == {"owner": "alice", "repo": "demo-tracking", "private": True}

        # Git steps: remote add, initial commit, push.
        argv = _argv_summary(fake_subprocess)
        assert any(
            "git remote add origin git@github.com:alice/demo-tracking.git" in c
            for c in argv
        ), argv
        assert any("git commit -m" in c for c in argv), argv
        assert any("git push -u origin main" in c for c in argv), argv

        # project_repo_url recorded in project.yaml.
        cfg = yaml.safe_load((target / "project.yaml").read_text())
        assert cfg["project_repo_url"] == "git@github.com:alice/demo-tracking.git"

    def test_uses_existing_repo_skips_create(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        monkeypatch.setattr(
            github_client, "repo_exists", lambda *_a, **_kw: True
        )

        def _unreachable_create(*_a: Any, **_kw: Any) -> dict[str, Any]:
            raise AssertionError(
                "create_repo must not be called when repo_exists returned True"
            )

        monkeypatch.setattr(github_client, "create_repo", _unreachable_create)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target))

        assert result.exit_code == 0, result.output
        # Remote still configured + push still attempted.
        argv = _argv_summary(fake_subprocess)
        assert any("git remote add origin" in c for c in argv)
        assert any("git push -u origin main" in c for c in argv)

    def test_public_flag_passes_private_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        monkeypatch.setattr(
            github_client, "repo_exists", lambda *_a, **_kw: False
        )
        captured: dict[str, Any] = {}

        def _fake_create(owner: str, repo: str, **kwargs: Any) -> dict[str, Any]:
            captured["private"] = kwargs.get("private")
            return {"ssh_url": "git@github.com:alice/demo-tracking.git"}

        monkeypatch.setattr(github_client, "create_repo", _fake_create)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target) + ["--public"])

        assert result.exit_code == 0, result.output
        assert captured["private"] is False


# ============================================================================
# Opt-out flags
# ============================================================================


class TestOptOuts:
    def test_no_remote_skips_everything(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
    ) -> None:
        # If the API was somehow contacted, this would explode.
        def _exploding(*_a: Any, **_kw: Any) -> Any:
            raise AssertionError("--no-remote must skip all GitHub API calls")

        monkeypatch.setattr(github_client, "resolve_token", _exploding)
        monkeypatch.setattr(github_client, "repo_exists", _exploding)
        monkeypatch.setattr(github_client, "create_repo", _exploding)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target) + ["--no-remote"])

        assert result.exit_code == 0, result.output
        # No remote commands (no remote add / push).
        argv = _argv_summary(fake_subprocess)
        assert not any("git remote add" in c for c in argv), argv
        assert not any("git push" in c for c in argv), argv

    def test_no_github_repo_skips_api_but_configures_remote(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        # API check + create must NOT be called.
        def _exploding(*_a: Any, **_kw: Any) -> Any:
            raise AssertionError(
                "--no-github-repo must skip repo_exists / create_repo"
            )

        monkeypatch.setattr(github_client, "repo_exists", _exploding)
        monkeypatch.setattr(github_client, "create_repo", _exploding)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(
            init_cmd, _base_args(target) + ["--no-github-repo"]
        )

        assert result.exit_code == 0, result.output
        # Remote still configured, push still attempted.
        argv = _argv_summary(fake_subprocess)
        assert any(
            "git remote add origin git@github.com:alice/demo-tracking.git" in c
            for c in argv
        ), argv
        assert any("git push -u origin main" in c for c in argv), argv

    def test_no_push_keeps_remote_skips_push(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        monkeypatch.setattr(
            github_client, "repo_exists", lambda *_a, **_kw: False
        )
        monkeypatch.setattr(
            github_client,
            "create_repo",
            lambda *_a, **_kw: {"ssh_url": "git@github.com:alice/demo-tracking.git"},
        )

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target) + ["--no-push"])

        assert result.exit_code == 0, result.output
        argv = _argv_summary(fake_subprocess)
        assert any("git remote add origin" in c for c in argv), argv
        assert not any("git push" in c for c in argv), argv


# ============================================================================
# Auth / token resolution failure
# ============================================================================


class TestMissingToken:
    def test_init_fails_fast_when_no_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(github_client, "resolve_token", lambda: None)

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target))

        assert result.exit_code != 0, result.output
        # Error message should point to all the resolution sources so the
        # operator knows what to fix.
        assert "GITHUB_TOKEN" in result.output
        assert "--no-remote" in result.output


# ============================================================================
# Project-yaml field recording
# ============================================================================


class TestProjectYamlFieldRecorded:
    def test_project_repo_url_absent_when_no_remote(
        self,
        tmp_path: Path,
        fake_subprocess: list[list[str]],
    ) -> None:
        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target) + ["--no-remote"])

        assert result.exit_code == 0, result.output
        cfg = yaml.safe_load((target / "project.yaml").read_text())
        # Pre-v0.7.6 projects didn't have the field; --no-remote yields the
        # same shape.
        assert cfg.get("project_repo_url") in (None, "")

    def test_project_repo_url_recorded_when_remote_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: list[list[str]],
        fake_token: str,
    ) -> None:
        monkeypatch.setattr(
            github_client, "repo_exists", lambda *_a, **_kw: False
        )
        monkeypatch.setattr(
            github_client,
            "create_repo",
            lambda *_a, **_kw: {"ssh_url": "git@github.com:alice/demo-tracking.git"},
        )

        target = tmp_path / "demo"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _base_args(target))

        assert result.exit_code == 0, result.output
        cfg = yaml.safe_load((target / "project.yaml").read_text())
        assert cfg["project_repo_url"] == "git@github.com:alice/demo-tracking.git"
