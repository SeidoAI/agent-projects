"""Tests for `tripwire.core.github_client`.

Thin httpx wrapper around the GitHub REST API used by `tripwire init` to
auto-create the project-tracking repo and configure the remote (v0.7.6
item A). Each test mocks httpx so we never touch the real network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from tripwire.core import github_client


class _StubResponse:
    """Minimal stand-in for `httpx.Response` — only exposes the bits the
    client uses (`status_code`, `json()`, `raise_for_status()`)."""

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=httpx.Request("GET", "https://api.github.com/"),
                response=httpx.Response(self.status_code),
            )


# ============================================================================
# repo_exists
# ============================================================================


class TestRepoExists:
    def test_returns_true_on_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_get(url: str, **_kw: Any) -> _StubResponse:
            assert url == "https://api.github.com/repos/seido/tripwire"
            return _StubResponse(200, {"name": "tripwire"})

        monkeypatch.setattr(httpx, "get", _fake_get)
        assert github_client.repo_exists("seido", "tripwire", token="t") is True

    def test_returns_false_on_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "get", lambda *_a, **_kw: _StubResponse(404))
        assert github_client.repo_exists("seido", "missing", token="t") is False

    def test_raises_on_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "get", lambda *_a, **_kw: _StubResponse(401))
        with pytest.raises(github_client.GitHubAuthError):
            github_client.repo_exists("seido", "anything", token="bad")

    def test_raises_on_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "get", lambda *_a, **_kw: _StubResponse(403))
        with pytest.raises(github_client.GitHubAuthError):
            github_client.repo_exists("seido", "anything", token="bad")


# ============================================================================
# create_repo
# ============================================================================


class TestCreateRepo:
    def test_calls_user_endpoint_for_self_owned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_post(url: str, **kwargs: Any) -> _StubResponse:
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            return _StubResponse(
                201,
                {
                    "name": "demo",
                    "ssh_url": "git@github.com:alice/demo.git",
                    "html_url": "https://github.com/alice/demo",
                },
            )

        monkeypatch.setattr(httpx, "post", _fake_post)
        # Stub _authenticated_owner to return "alice" so owner == self.
        monkeypatch.setattr(
            github_client, "_authenticated_owner", lambda token: "alice"
        )

        result = github_client.create_repo(
            "alice",
            "demo",
            private=True,
            description="Demo repo",
            token="t",
        )

        assert captured["url"] == "https://api.github.com/user/repos"
        assert captured["json"]["name"] == "demo"
        assert captured["json"]["private"] is True
        assert captured["json"]["description"] == "Demo repo"
        assert captured["json"]["auto_init"] is False
        assert result["ssh_url"] == "git@github.com:alice/demo.git"

    def test_calls_orgs_endpoint_for_org_owned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_post(url: str, **kwargs: Any) -> _StubResponse:
            captured["url"] = url
            return _StubResponse(201, {"ssh_url": "git@github.com:SeidoAI/demo.git"})

        monkeypatch.setattr(httpx, "post", _fake_post)
        monkeypatch.setattr(
            github_client, "_authenticated_owner", lambda token: "alice"
        )

        github_client.create_repo(
            "SeidoAI",
            "demo",
            private=False,
            description="",
            token="t",
        )

        assert captured["url"] == "https://api.github.com/orgs/SeidoAI/repos"

    def test_raises_on_auth_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "post", lambda *_a, **_kw: _StubResponse(401))
        monkeypatch.setattr(
            github_client, "_authenticated_owner", lambda token: "alice"
        )
        with pytest.raises(github_client.GitHubAuthError):
            github_client.create_repo(
                "alice", "demo", private=True, description="", token="bad"
            )


# ============================================================================
# resolve_token
# ============================================================================


class TestResolveToken:
    def test_prefers_GITHUB_TOKEN_over_GH_TOKEN(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "primary")
        monkeypatch.setenv("GH_TOKEN", "fallback")
        assert github_client.resolve_token() == "primary"

    def test_uses_GH_TOKEN_when_GITHUB_TOKEN_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", "fallback")
        assert github_client.resolve_token() == "fallback"

    def test_falls_back_to_gh_hosts_yml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        hosts = tmp_path / "hosts.yml"
        hosts.write_text(
            "github.com:\n"
            "  oauth_token: gh-cli-token\n"
            "  user: alice\n"
            "  git_protocol: ssh\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(github_client, "_GH_HOSTS_PATH", hosts)
        assert github_client.resolve_token() == "gh-cli-token"

    def test_returns_none_when_all_sources_miss(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setattr(github_client, "_GH_HOSTS_PATH", tmp_path / "missing.yml")
        assert github_client.resolve_token() is None

    def test_handles_malformed_gh_hosts_yml_gracefully(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If the gh hosts file isn't parseable or has an unexpected
        shape, we fall through to None rather than crashing."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        hosts = tmp_path / "hosts.yml"
        hosts.write_text("not: [valid yaml here", encoding="utf-8")
        monkeypatch.setattr(github_client, "_GH_HOSTS_PATH", hosts)
        assert github_client.resolve_token() is None


# ============================================================================
# _authenticated_owner
# ============================================================================


class TestAuthenticatedOwner:
    def test_returns_login_from_user_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_get(url: str, **_kw: Any) -> _StubResponse:
            assert url == "https://api.github.com/user"
            return _StubResponse(200, {"login": "alice"})

        monkeypatch.setattr(httpx, "get", _fake_get)
        assert github_client._authenticated_owner("t") == "alice"

    def test_returns_none_on_unauth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "get", lambda *_a, **_kw: _StubResponse(401))
        assert github_client._authenticated_owner("bad") is None
