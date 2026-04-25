"""PM-review service placeholder (v2 stub).

PM reviews are the PM agent's structured checks against PRs to the
project repo. v2 will run them via ``tripwire.containers`` orchestration
+ tripwire.core; v1 has no orchestration, so every method raises
``NotImplementedError`` and every route returns 501.

No imports of ``tripwire.core.pm_review`` (it does not yet exist).
See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

_NI_MESSAGE = (
    "tripwire.ui PM-review feature is not yet implemented (v2). "
    "See docs/agent-containers.md."
)


# ---------------------------------------------------------------------------
# DTOs (OpenAPI-only; never returned in v1)
# ---------------------------------------------------------------------------


class CheckResultDTO(BaseModel):
    """Outcome of a single PM-review check."""

    name: str
    status: str
    message: str | None = None


class PmReviewSummary(BaseModel):
    """Short descriptor of a pending/completed PM review."""

    pr_number: int
    status: str
    updated_at: datetime


class PmReviewDetail(BaseModel):
    """Full PM-review record with per-check results."""

    pr_number: int
    status: str
    updated_at: datetime
    checks: list[CheckResultDTO]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PmReviewService:
    """Placeholder PM-review service.

    Every method raises :class:`NotImplementedError`; the v2
    implementation will live alongside ``tripwire.containers``.
    """

    def list_pending(self, project_dir: Path) -> list[PmReviewSummary]:
        raise NotImplementedError(_NI_MESSAGE)

    def get_review(self, project_dir: Path, pr_number: int) -> PmReviewDetail:
        raise NotImplementedError(_NI_MESSAGE)

    def run_review(self, project_dir: Path, pr_number: int) -> PmReviewDetail:
        raise NotImplementedError(_NI_MESSAGE)
