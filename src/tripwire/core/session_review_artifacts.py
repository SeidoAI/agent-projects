"""Pure parsers + report builder for `session review-artifacts`.

v0.7.9 §A2 + §A3. Reads ``sessions/<sid>/self-review.md`` and
``sessions/<sid>/pm-response.yaml`` and produces a side-by-side
report — what the agent flagged, how the PM responded, and which
self-review items remain unaddressed.

Sibling to :mod:`tripwire.core.session_review` (which reviews a PR
diff against the session's issue ACs). The two have different
inputs and different downstream consumers; see
``decisions.md`` for why this is a separate module rather than an
extension to the existing review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SelfReviewItem:
    lens: int
    text: str


@dataclass
class PmResponseItem:
    quote_excerpt: str
    decision: str | None = None
    follow_up: str | None = None
    fix_commit: str | None = None
    note: str | None = None


@dataclass
class PairedItem:
    self_review_text: str
    self_review_lens: int
    pm_response: PmResponseItem | None


@dataclass
class ReviewArtifactsReport:
    session_id: str
    self_review_present: bool
    pm_response_present: bool
    pairs: list[PairedItem] = field(default_factory=list)
    unaddressed: list[SelfReviewItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


_LENS_HEADING_RE = re.compile(r"^##\s+Lens\s+(\d+)\s*:", re.MULTILINE)
_BULLET_RE = re.compile(r"^[-*]\s+(.+?)$")


def parse_self_review_items(body: str) -> list[SelfReviewItem]:
    """Walk a self-review.md and return one item per ``- bullet`` line
    under each ``## Lens N:`` heading.

    The matcher intentionally:
      - ignores anything outside a ``## Lens N:`` section (preamble,
        section headers, free-form prose)
      - treats blank lines, ``<placeholder>`` lines, and indented
        content as not-a-bullet so the four-lens template's ``<...>``
        guidance lines don't show up as items
    """
    items: list[SelfReviewItem] = []
    current_lens: int | None = None
    for line in body.splitlines():
        stripped = line.rstrip()
        m = _LENS_HEADING_RE.match(stripped)
        if m:
            current_lens = int(m.group(1))
            continue
        if current_lens is None:
            continue
        b = _BULLET_RE.match(stripped)
        if not b:
            continue
        text = b.group(1).strip()
        # Skip checkbox-only ("[ ] " / "[x] ") prefixes — keep the body.
        text = re.sub(r"^\[[ xX]\]\s*", "", text)
        # Skip the template's literal ``<...>`` placeholder bullets and
        # the ``<example item — replace…>`` guide lines.
        if text.startswith("<example item") or text.startswith("<replace"):
            continue
        items.append(SelfReviewItem(lens=current_lens, text=text))
    return items


def parse_pm_response_items(body: str) -> list[PmResponseItem]:
    """Parse pm-response.yaml and return its ``items[]`` entries.

    Raises ``ValueError`` on malformed YAML.
    """
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise ValueError(f"pm-response.yaml malformed: {exc}") from exc
    if not isinstance(data, dict):
        return []
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        return []
    parsed: list[PmResponseItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        parsed.append(
            PmResponseItem(
                quote_excerpt=str(raw.get("quote_excerpt", "")),
                decision=(
                    str(raw["decision"]) if raw.get("decision") is not None else None
                ),
                follow_up=(
                    str(raw["follow_up"])
                    if raw.get("follow_up") is not None
                    else None
                ),
                fix_commit=(
                    str(raw["fix_commit"])
                    if raw.get("fix_commit") is not None
                    else None
                ),
                note=str(raw["note"]) if raw.get("note") is not None else None,
            )
        )
    return parsed


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _match_pm_response(
    sr_item: SelfReviewItem, pm_items: list[PmResponseItem]
) -> PmResponseItem | None:
    """Return the first pm-response item whose ``quote_excerpt`` is a
    case-insensitive substring of the self-review text, or vice versa.

    Symmetric matching: the PM may copy a phrase from the self-review
    (so ``quote_excerpt`` is a substring of the SR text), or quote a
    longer rewrite of the SR item (so the SR text is a substring of
    ``quote_excerpt``). Both should pair.
    """
    sr_lower = sr_item.text.lower()
    for pm in pm_items:
        q = pm.quote_excerpt.strip().lower()
        if not q:
            continue
        if q in sr_lower or sr_lower in q:
            return pm
    return None


def build_report(project_dir: Path, session_id: str) -> ReviewArtifactsReport:
    """Read both artifacts (if present) and produce a paired report.

    Missing files are tolerated: the report's flags
    (``self_review_present`` / ``pm_response_present``) tell the
    caller what was on disk.
    """
    sdir = project_dir / "sessions" / session_id
    sr_path = sdir / "self-review.md"
    pr_path = sdir / "pm-response.yaml"

    self_review_present = sr_path.is_file()
    pm_response_present = pr_path.is_file()

    sr_items: list[SelfReviewItem] = []
    if self_review_present:
        sr_items = parse_self_review_items(sr_path.read_text(encoding="utf-8"))

    pm_items: list[PmResponseItem] = []
    if pm_response_present:
        pm_items = parse_pm_response_items(pr_path.read_text(encoding="utf-8"))

    pairs: list[PairedItem] = []
    unaddressed: list[SelfReviewItem] = []
    for sr in sr_items:
        match = _match_pm_response(sr, pm_items) if pm_items else None
        pairs.append(
            PairedItem(
                self_review_text=sr.text,
                self_review_lens=sr.lens,
                pm_response=match,
            )
        )
        if match is None:
            unaddressed.append(sr)

    return ReviewArtifactsReport(
        session_id=session_id,
        self_review_present=self_review_present,
        pm_response_present=pm_response_present,
        pairs=pairs,
        unaddressed=unaddressed,
    )
