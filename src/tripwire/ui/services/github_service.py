"""GitHub integration service placeholder (v2 stub).

v2 will shell out to the ``gh`` CLI via ``subprocess`` to fetch PR
status, CI checks, and reviews. v1 has no live sessions to overlay PR
state on, so every method raises ``NotImplementedError`` and every
route returns 501.

No ``subprocess`` imports live here — the shell-out lives in v2.
See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

_NI_MESSAGE = (
    "tripwire.ui GitHub integration is not yet implemented (v2). "
    "See docs/tripwire-containers.md."
)


# ---------------------------------------------------------------------------
# DTOs (OpenAPI-only; never returned in v1)
# ---------------------------------------------------------------------------


class PRSummary(BaseModel):
    """Short description of a GitHub pull request."""

    number: int
    title: str
    state: str
    head: str
    base: str
    url: str
    author: str
    updated_at: datetime


class CheckRun(BaseModel):
    """Single CI check run on a PR."""

    name: str
    status: str
    conclusion: str | None = None
    url: str | None = None


class Review(BaseModel):
    """Reviewer comment/approval on a PR."""

    reviewer: str
    state: str
    submitted_at: datetime | None = None
    body: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GitHubService:
    """Placeholder GitHub integration service.

    Every method raises :class:`NotImplementedError`; the v2
    implementation will wrap the ``gh`` CLI.
    """

    def list_prs(self, repo: str, head: str | None = None) -> list[PRSummary]:
        raise NotImplementedError(_NI_MESSAGE)

    def get_checks(self, repo: str, pr_number: int) -> list[CheckRun]:
        raise NotImplementedError(_NI_MESSAGE)

    def get_reviews(self, repo: str, pr_number: int) -> list[Review]:
        raise NotImplementedError(_NI_MESSAGE)

    def merge_pr(self, repo: str, pr_number: int) -> None:
        raise NotImplementedError(_NI_MESSAGE)

    def close_pr(self, repo: str, pr_number: int) -> None:
        raise NotImplementedError(_NI_MESSAGE)
