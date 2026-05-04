"""PM-review workflow status (KUI-150 / J1).

PM-review is the workflow the project manager runs against an
in_review session at handover. It re-runs the 10 most consequential
existing validators (see :mod:`tripwire.core.pm_review.checks`),
synthesises a verdict, writes ``sessions/<sid>/artifacts/pm-review.md``,
and emits a ``pm_review.completed`` event under workflow ``pm-review``
in the events log.

The 10 checks are *literal re-runs* of existing validator functions —
no logic is duplicated. See ``decisions.md`` D1 in the project-tracking
worktree for the reasoning. The runner shells out to
:func:`tripwire.core.validator.validate_project` (the same surface
``tripwire transition`` calls) and partitions the report by validator
id, so every check that lands in ``ALL_CHECKS`` automatically continues
to be exercised by pm-review.

Public surface:

- :func:`run_pm_review` — execute the review for one session, return
  a :class:`PMReviewVerdict`, write the artifact, emit the event.
- :class:`PMReviewVerdict` — the structured outcome.
- :class:`PMReviewCheck` — one row per named check.
"""

from __future__ import annotations

from tripwire.core.pm_review.runner import (
    PMReviewCheck,
    PMReviewVerdict,
    run_pm_review,
)

__all__ = ["PMReviewCheck", "PMReviewVerdict", "run_pm_review"]
