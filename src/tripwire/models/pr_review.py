"""Pydantic schema for `sessions/<sid>/pr-review.yaml`.

v0.12: introduced to close the PM-review enforcement gap. Two sessions
in kb-pivot merged with placeholder `verified.md` files because the
PM agent ran the thin `tripwire session review` CLI (which produced a
`verdict: approved` artifact for any session) and skipped the
substantive `/pm-session-review` slash command. The pr-review.yaml
artifact records the substance of that review — per-issue AC evidence,
four-lens scrutiny, external-reviewer signals, threshold-finding
resolution — and the validator enforces all of it.

See `src/tripwire/core/validator/checks/pr_review.py` for the four
v0.12 validator rules that gate on this schema's content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PrRef(BaseModel):
    """One PR's identifying triple: repo slug, number, and head SHA."""

    model_config = ConfigDict(extra="forbid")

    repo: str
    number: int
    head_sha: str


class PrPair(BaseModel):
    """The two PRs a session typically opens — code (target repo) and
    PT (project-tracking repo). Either may be omitted for sessions
    that only touch one side."""

    model_config = ConfigDict(extra="forbid")

    code: PrRef | None = None
    pt: PrRef | None = None


AcDecision = Literal["verified", "deferred", "rejected"]
"""Per-AC verification outcome.

- ``verified`` — evidence cited; AC met.
- ``deferred`` — AC isn't met but is being deferred to a follow-up
  issue. The follow-up's key should be recorded in `note`.
- ``rejected`` — AC was rejected as out-of-scope or unworkable;
  rationale recorded in `note`.
"""


class AcVerification(BaseModel):
    """One acceptance criterion's verification record."""

    model_config = ConfigDict(extra="forbid")

    text: str
    """The AC text from the issue."""

    verified_by: list[str] = Field(default_factory=list)
    """Concrete evidence — file:line citations or short evidence strings.

    Placeholders ("manual verification needed", "TBD", empty arrays)
    are caught by the `pr_review/missing_evidence` validator rule.
    """

    decision: AcDecision = "verified"
    note: str | None = None


class IssueVerification(BaseModel):
    """All ACs for one issue that this session implements."""

    model_config = ConfigDict(extra="forbid")

    key: str
    acs: list[AcVerification] = Field(default_factory=list)


FindingDecision = Literal["fixed", "accepted", "deferred", "rejected"]
"""How a four-lens or external-review finding was resolved.

- ``fixed`` — addressed in a follow-up commit on the PR; commit SHA in
  `fix_commit`.
- ``accepted`` — known limitation, intentional; rationale in `note`.
- ``deferred`` — addressed in a follow-up issue; key in `follow_up`.
- ``rejected`` — disagreed with the finding; rationale in `note`.
"""


class FourLensFinding(BaseModel):
    """One finding under one of the four lenses (AC-met-but-not-really,
    unilateral decisions, skipped workflow, quality degradation)."""

    model_config = ConfigDict(extra="forbid")

    text: str
    severity: int = Field(ge=0, le=100)
    decision: FindingDecision
    fix_commit: str | None = None
    follow_up: str | None = None
    note: str | None = None


class FourLensCategory(BaseModel):
    """Findings under one of the four lenses."""

    model_config = ConfigDict(extra="forbid")

    findings: list[FourLensFinding] = Field(default_factory=list)


class FourLens(BaseModel):
    """The four-lens scrutiny output."""

    model_config = ConfigDict(extra="forbid")

    ac_met_but_not_really: FourLensCategory = Field(default_factory=FourLensCategory)
    unilateral_decisions: FourLensCategory = Field(default_factory=FourLensCategory)
    skipped_workflow: FourLensCategory = Field(default_factory=FourLensCategory)
    quality_degradation: FourLensCategory = Field(default_factory=FourLensCategory)


class CodexReview(BaseModel):
    """Record of the external-reviewer (codex / equivalent) PR comment."""

    model_config = ConfigDict(extra="forbid")

    posted_at: datetime
    comment_url: str


class CodeReviewSkillFinding(BaseModel):
    """One finding from the configured code-review skill (e.g.
    `superpowers:code-review:code-review`)."""

    model_config = ConfigDict(extra="forbid")

    severity: int = Field(ge=0, le=100)
    category: str
    location: str
    text: str
    decision: FindingDecision
    fix_commit: str | None = None
    follow_up: str | None = None
    note: str | None = None


class CodeReviewSkillRun(BaseModel):
    """Record of one code-review skill invocation against the PR."""

    model_config = ConfigDict(extra="forbid")

    skill: str
    invoked_at: datetime
    findings: list[CodeReviewSkillFinding] = Field(default_factory=list)


class ExternalReviews(BaseModel):
    """External-reviewer signals captured during PM review.

    `codex` is the conventional name for the project's external-
    reviewer mention (e.g. `@codex`). If a project configures
    `project.yaml.review.external_reviewer_mention` to a different
    value, the PM still records the URL under `codex` for now —
    the field name is conventional, not bound to a specific service.
    """

    model_config = ConfigDict(extra="forbid")

    codex: CodexReview | None = None
    code_review_skill: CodeReviewSkillRun | None = None


class ThresholdUnaddressedFinding(BaseModel):
    """A single finding above the configured severity threshold that
    has not been addressed (no `fixed`/`deferred`/`rejected` decision
    with matching evidence)."""

    model_config = ConfigDict(extra="forbid")

    severity: int = Field(ge=0, le=100)
    category: str
    location: str
    reason: str


class ThresholdFindings(BaseModel):
    """Aggregate of findings above the configured severity threshold.

    The PM populates this after applying decisions; the
    `pr_review/threshold_findings_unaddressed` validator rule fires
    if `unaddressed` is non-empty, blocking the transition to
    `verified`/`completed`.
    """

    model_config = ConfigDict(extra="forbid")

    threshold: int = Field(ge=0, le=100, default=65)
    count_above: int = 0
    count_addressed: int = 0
    unaddressed: list[ThresholdUnaddressedFinding] = Field(default_factory=list)


PrReviewVerdict = Literal["approved", "request_changes", "blocked"]


class PrReview(BaseModel):
    """Top-level schema for `sessions/<sid>/pr-review.yaml`.

    The PM authors this during the in_review window. v0.12 validator
    rules (`pr_review/missing_evidence`,
    `pr_review/threshold_findings_unaddressed`,
    `pr_review/external_reviewer_missing`,
    `pr_review/code_review_skill_missing`) gate transitions on this
    file's content; missing-file enforcement is handled by
    `check_artifact_presence` via the manifest entry's
    `produced_at: in_review`.
    """

    model_config = ConfigDict(extra="forbid")

    read_at: datetime
    read_by: str = "pm"
    pr: PrPair = Field(default_factory=PrPair)
    issues: list[IssueVerification] = Field(default_factory=list)
    four_lens: FourLens = Field(default_factory=FourLens)
    external_reviews: ExternalReviews = Field(default_factory=ExternalReviews)
    threshold_findings: ThresholdFindings = Field(default_factory=ThresholdFindings)
    verdict: PrReviewVerdict = "approved"
