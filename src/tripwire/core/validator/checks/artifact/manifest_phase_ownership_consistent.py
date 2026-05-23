"""Manifest ownership/produced-by/produced-at alignment."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _load_manifest


def check_manifest_phase_ownership_consistent(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """Warn if PM owns an executing/in_review artifact authored by an agent.

    The PM agent steers scoping and planning; once a session is in
    `executing` or `in_review`, the execution/verification agent
    typically authors the artifacts. A manifest that says PM *owns*
    something an agent *produced* likely encodes the v0.5 bug where
    the PM was charged with writing files the execution agent should
    have written.

    v0.12: only fires when ``owned_by != produced_by``. PM-owned-and-
    PM-produced artifacts (e.g. ``pr-review.yaml``: produced_at=in_review,
    produced_by=pm, owned_by=pm) are deliberately PM work during the
    review window and shouldn't trip the heuristic.
    """
    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []
    results: list[CheckResult] = []
    for entry in manifest.artifacts:
        if (
            entry.owned_by == "pm"
            and entry.produced_at in ("executing", "in_review")
            and entry.produced_by != "pm"
        ):
            results.append(
                CheckResult(
                    code="manifest_schema/phase_ownership_consistent",
                    severity="warning",
                    file=paths.TEMPLATES_ARTIFACTS_MANIFEST,
                    field="owned_by",
                    message=(
                        f"artifact '{entry.name}' owned by pm but produced at "
                        f"{entry.produced_at} by {entry.produced_by} — "
                        "consider aligning ownership with the producing agent"
                    ),
                )
            )
    return results
