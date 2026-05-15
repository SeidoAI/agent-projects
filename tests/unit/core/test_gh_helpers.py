"""Unit tests for the consolidated ``gh`` helper module.

Every public function has three test shapes:

- happy path: ``gh`` exits 0, the helper returns the parsed payload.
- error path: ``gh`` exits non-zero, the helper raises :class:`GhError`
  carrying the stderr.
- missing-binary path: ``subprocess.run`` raises
  :class:`FileNotFoundError`, the helper raises :class:`GhError` with
  an actionable "gh not installed" message.

The internals of ``_run_gh`` are exercised indirectly through the
public surface — keeping the mock target at ``subprocess.run`` mirrors
how real callers fail.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tripwire.core import gh_helpers
from tripwire.core.gh_helpers import (
    GhError,
    get_merged_pr_for_branch,
    gh_pr_close,
    gh_pr_ready,
)


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> Any:
    class _R:
        pass

    r = _R()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


# ---------------------------------------------------------------------------
# get_merged_pr_for_branch
# ---------------------------------------------------------------------------


class TestGetMergedPrForBranch:
    def test_happy_path_returns_parsed_dict(self, monkeypatch):
        """Real `gh pr list` JSON output shape — single merged PR."""
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            captured["cwd"] = kwargs.get("cwd")
            payload = [
                {
                    "number": 42,
                    "mergedAt": "2026-05-01T12:00:00Z",
                    "state": "MERGED",
                    "mergeCommit": {"oid": "abc123"},
                    "headRefName": "feat/foo",
                }
            ]
            return _completed(0, stdout=json.dumps(payload))

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)

        pr = get_merged_pr_for_branch("feat/foo", cwd=Path("/tmp/wt"))

        assert pr is not None
        assert pr["number"] == 42
        assert pr["mergedAt"] == "2026-05-01T12:00:00Z"
        assert pr["state"] == "MERGED"
        # gh invoked with the expected flags + worktree cwd.
        assert captured["cmd"][:5] == ["gh", "pr", "list", "--head", "feat/foo"]
        assert "--state" in captured["cmd"]
        assert "merged" in captured["cmd"]
        assert captured["cwd"] == "/tmp/wt"

    def test_empty_array_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(0, stdout="[]"),
        )
        assert get_merged_pr_for_branch("feat/foo") is None

    def test_empty_stdout_returns_none(self, monkeypatch):
        """``gh`` occasionally returns empty stdout instead of `[]` —
        treat both as "no merged PR" rather than raising."""
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(0, stdout=""),
        )
        assert get_merged_pr_for_branch("feat/foo") is None

    def test_non_zero_exit_raises_gh_error(self, monkeypatch):
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(1, stderr="network down"),
        )
        with pytest.raises(GhError) as exc:
            get_merged_pr_for_branch("feat/foo")
        assert "network down" in str(exc.value)
        assert "exit=1" in str(exc.value)

    def test_gh_not_installed_raises_gh_error(self, monkeypatch):
        def fake_run(*a, **k):
            raise FileNotFoundError(2, "No such file or directory: 'gh'")

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        with pytest.raises(GhError) as exc:
            get_merged_pr_for_branch("feat/foo")
        assert "gh not installed" in str(exc.value)

    def test_invalid_json_raises_gh_error(self, monkeypatch):
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(0, stdout="not json"),
        )
        with pytest.raises(GhError) as exc:
            get_merged_pr_for_branch("feat/foo")
        assert "invalid JSON" in str(exc.value)

    def test_subprocess_timeout_raises_gh_error(self, monkeypatch):
        def fake_run(*a, **k):
            raise subprocess.TimeoutExpired(cmd="gh pr list", timeout=15)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        with pytest.raises(GhError) as exc:
            get_merged_pr_for_branch("feat/foo")
        assert "gh subprocess failed" in str(exc.value)


# ---------------------------------------------------------------------------
# gh_pr_ready
# ---------------------------------------------------------------------------


class TestGhPrReady:
    def test_happy_path_invokes_gh_pr_ready(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_ready(42)
        assert captured["cmd"] == ["gh", "pr", "ready", "42"]

    def test_undo_appends_flag(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_ready("https://github.com/org/repo/pull/10", undo=True)
        assert captured["cmd"] == [
            "gh",
            "pr",
            "ready",
            "https://github.com/org/repo/pull/10",
            "--undo",
        ]

    def test_non_zero_exit_raises_gh_error(self, monkeypatch):
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(1, stderr="not a PR"),
        )
        with pytest.raises(GhError) as exc:
            gh_pr_ready(42)
        assert "not a PR" in str(exc.value)

    def test_gh_not_installed_raises_gh_error(self, monkeypatch):
        def fake_run(*a, **k):
            raise FileNotFoundError(2, "No such file or directory: 'gh'")

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        with pytest.raises(GhError) as exc:
            gh_pr_ready(42)
        assert "gh not installed" in str(exc.value)


# ---------------------------------------------------------------------------
# gh_pr_close
# ---------------------------------------------------------------------------


class TestGhPrClose:
    def test_happy_path_invokes_gh_pr_close(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_close(42)
        assert captured["cmd"] == ["gh", "pr", "close", "42"]

    def test_comment_appended(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_close(42, comment="abandoned")
        assert captured["cmd"] == [
            "gh",
            "pr",
            "close",
            "42",
            "--comment",
            "abandoned",
        ]

    def test_url_target_accepted(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_close("https://github.com/org/repo/pull/10")
        assert captured["cmd"] == [
            "gh",
            "pr",
            "close",
            "https://github.com/org/repo/pull/10",
        ]

    def test_non_zero_exit_raises_gh_error(self, monkeypatch):
        monkeypatch.setattr(
            gh_helpers.subprocess,
            "run",
            lambda *a, **k: _completed(1, stderr="already closed"),
        )
        with pytest.raises(GhError) as exc:
            gh_pr_close(42)
        assert "already closed" in str(exc.value)

    def test_gh_not_installed_raises_gh_error(self, monkeypatch):
        def fake_run(*a, **k):
            raise FileNotFoundError(2, "No such file or directory: 'gh'")

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        with pytest.raises(GhError) as exc:
            gh_pr_close(42)
        assert "gh not installed" in str(exc.value)

    def test_cwd_forwarded(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cwd"] = kwargs.get("cwd")
            return _completed(0)

        monkeypatch.setattr(gh_helpers.subprocess, "run", fake_run)
        gh_pr_close(42, cwd=Path("/tmp/wt"))
        assert captured["cwd"] == "/tmp/wt"
