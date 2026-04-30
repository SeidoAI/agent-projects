"""Phase-transition tripwire — KUI-138 / B4.

Fires on ``session.complete`` when the project's ``phase:`` has been
advanced past the natural end of the previous phase but issues
labelled with that previous phase are still open. The pattern this
catches is the v0.8.x premature-close incident: PM bumps
``phase: executing → reviewing`` while ``in_progress`` issues
remain.

The tripwire body lives inline as ``_VARIATIONS`` (matching
:mod:`tripwire._internal.tripwires.self_review`) per the design
decision recorded in ``decisions.md``: there is no markdown-loading
path in the substrate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from tripwire._internal.tripwires import Tripwire, TripwireContext

# Phases the project can hold the work in. Linear progression matches
# ``models.project.ProjectPhase``: scoping → scoped → executing →
# reviewing.
PREVIOUS_PHASE: dict[str, str] = {
    "scoped": "scoping",
    "executing": "scoped",
    "reviewing": "executing",
}

# Issue statuses that count as "still open" — i.e. work the agent
# hasn't finished yet. Mirrors the convention used by other validators
# (verified, done, canceled are terminal; everything else is open).
_OPEN_STATUSES = {"backlog", "todo", "in_progress", "in_review"}

# Label convention: issues are tagged with ``phase:<name>`` to scope
# them to a project phase. The body of an Issue YAML uses
# ``labels: [phase:executing, ...]`` — the validator does not enforce
# this prefix today, so the tripwire treats it as a soft convention.
_PHASE_LABEL_PREFIX = "phase:"

_VARIATIONS: tuple[str, ...] = (
    """\
The project's `phase:` has been advanced — but at least one issue
that's still labelled with the previous phase isn't closed yet. This
is the premature-close pattern: the PM (you) bumps the phase before
the actual work in the previous phase has crossed the finish line.

Before declaring this session done, walk every issue tagged with the
previous phase's `phase:<prev>` label. For each one that's still in a
non-terminal status (`backlog` / `todo` / `in_progress` / `in_review`),
either:

  - Close it (move it to `done` / `verified` / `canceled` with a
    rationale), OR
  - Roll the project's `phase:` back to the prior value, OR
  - Re-tag the issue with the current phase if the work has actually
    moved across the boundary.

Re-run with `--ack` after the marker file lists fix-commit SHAs OR
declares `declared_no_findings: true`.
""",
    """\
Stop. The project is in `phase: <X>` but issues with
`phase:<X-1>` labels are still open. The phase bump preceded the
work, not followed it.

Walk the issues directory. For every issue whose labels contain
`phase:<previous-phase>` and whose `status:` is one of `backlog`,
`todo`, `in_progress`, or `in_review`:

  1. Decide: should this issue actually be done? If yes, close it
     and record the closing commit. If no, the phase bump was
     premature — revert it.
  2. If the issue's scope drifted across the phase boundary, re-tag
     it with the current phase and document the re-scope in
     decisions.md.

The `--ack` marker requires fix-commit SHAs OR
`declared_no_findings: true` to be substantive.
""",
    """\
A phase transition is a contract: every issue scoped to the previous
phase has been resolved. Right now, that contract is broken — at
least one issue with a `phase:<prev>` label is still open while the
project carries a later `phase:` value.

Two recovery paths, pick exactly one:

  Path A — Finish the prev-phase work. Close every open
  `phase:<prev>` issue (status → `done` / `verified` /
  `canceled`) and reference the closing commit.
  Path B — Roll the phase back. Edit `project.yaml` to restore the
  prior `phase:` value, then re-evaluate when the prev-phase work
  has actually completed.

Whichever you pick, document it in `sessions/<sid>/self-review.md`
and re-run with `--ack`. The marker is rejected if it lacks
fix-commit SHAs and does not declare `declared_no_findings: true`.
""",
)


class PhaseTransitionTripwire(Tripwire):
    """Block ``session.complete`` when phase moved past open prev-phase issues."""

    id: ClassVar[str] = "phase-transition"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    def fire(self, ctx: TripwireContext) -> str:
        idx = ctx.variation_index(len(_VARIATIONS))
        return _VARIATIONS[idx]

    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        marker = ctx.ack_path(self.id)
        if not marker.is_file():
            return False
        return _marker_substantive(marker)

    def should_fire(self, ctx: TripwireContext) -> bool:
        """Fire iff the project advanced past a phase with open issues."""
        return _phase_contract_broken(ctx.project_dir)


def _phase_contract_broken(project_dir: Path) -> bool:
    from tripwire.core.store import load_project
    from tripwire.core.validator import load_context

    try:
        project = load_project(project_dir)
    except Exception:
        return False

    current = getattr(project.phase, "value", str(project.phase))
    prev = PREVIOUS_PHASE.get(current)
    if prev is None:
        return False

    try:
        ctx = load_context(project_dir)
    except Exception:
        return False

    prev_label = f"{_PHASE_LABEL_PREFIX}{prev}"
    for entity in ctx.issues:
        issue = entity.model
        labels = list(getattr(issue, "labels", []) or [])
        if prev_label not in labels:
            continue
        status = getattr(issue, "status", "")
        status_str = getattr(status, "value", str(status)).lower()
        if status_str in _OPEN_STATUSES:
            return True
    return False


def _marker_substantive(marker_path: Path) -> bool:
    """Same substantiveness check as :class:`SelfReviewTripwire`."""
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    commits = data.get("fix_commits")
    declared = data.get("declared_no_findings")
    has_commits = isinstance(commits, list) and any(
        isinstance(s, str) and s.strip() for s in commits
    )
    return bool(has_commits or declared is True)


__all__ = ["PREVIOUS_PHASE", "PhaseTransitionTripwire"]
