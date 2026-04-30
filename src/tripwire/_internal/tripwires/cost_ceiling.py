"""Cost-ceiling tripwire — KUI-142 / B8.

Fires on ``session.complete`` when the session's cumulative cost
(computed from the claude stream-json log via the existing
``tripwire.core.session_cost.compute_session_cost``) exceeds a
threshold (default $5.00). Per-project override:
``project.yaml.tripwires.extra`` for an entry with ``id:
cost-ceiling`` and ``params: {ceiling_usd: N}``.

The pattern this catches: long sessions that quietly burn API
credits. The PM hits API limits in the middle of validation-hardening
work and only finds out post-hoc.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import yaml

from tripwire._internal.tripwires import Tripwire, TripwireContext
from tripwire.core.session_cost import compute_session_cost

DEFAULT_COST_CEILING_USD = 5.0


_VARIATIONS: tuple[str, ...] = (
    """\
This session has crossed the cost-ceiling threshold. The pattern this
tripwire catches is the "long-tail spend" — sessions that quietly
burn API credits while the agent grinds on a sub-problem the PM
didn't expect to be expensive.

Before completing the session:

  1. Check `tripwire session cost <sid>` for the breakdown.
  2. Look at the high-cost areas. Was this expected (e.g. a long
     codex review pass)? Document it.
  3. If unexpected, the cost-ceiling for this project may be too
     low — bump it explicitly (and document why) rather than just
     `--ack`-ing.

Re-run with `--ack` after the marker carries fix-commit SHAs OR
`declared_no_findings: true`.
""",
    """\
Stop. Cumulative cost for this session is over the ceiling. The
$5 default is intentionally conservative — it's a smoke alarm, not a
hard cap. Sessions that cross it deserve a few seconds of
introspection before completing.

Concretely:

  - `tripwire session cost <sid>` → walk the per-category split.
  - If the spend is justified (long review, large codebase), update
    `project.yaml.tripwires.extra` for `id: cost-ceiling` with
    `params: {ceiling_usd: N}` to a calibrated value AND note the
    rationale in `decisions.md`.
  - If the spend is symptomatic of a runaway, do a post-mortem
    note in self-review.md identifying the cause.

Re-run `--ack`. Marker is rejected without fix-commit SHAs OR
`declared_no_findings: true`.
""",
    """\
The cost-ceiling for this project is the contract: spend more than
this and we want a conscious acknowledgement, not silent acceptance.
You've crossed it. That's not necessarily a bug — but it deserves a
deliberate response.

Pick one:

  Path A — Justify and recalibrate. The spend was correct for what
  the work needed. Update the per-project ceiling in
  `project.yaml.tripwires.extra` (`params: {ceiling_usd: N}`) and
  document the new floor in `decisions.md`.
  Path B — Diagnose the runaway. The spend was symptomatic. In
  `sessions/<sid>/self-review.md`, name the runaway, propose a
  guardrail (e.g. tighter scoping, a kill-switch on a specific
  loop) and file a follow-up issue.

Re-run with `--ack`. The marker requires SHAs OR `declared_no_findings: true`.
""",
)


class CostCeilingTripwire(Tripwire):
    """Block when cumulative session cost crosses the configured ceiling."""

    id: ClassVar[str] = "cost-ceiling"
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
        ceiling = _read_ceiling(ctx.project_dir)
        try:
            breakdown = compute_session_cost(ctx.project_dir, ctx.session_id)
        except Exception:
            return False
        return breakdown.total_usd > ceiling


def _read_ceiling(project_dir: Path) -> float:
    """Resolve the ceiling from project.yaml or fall back to default."""
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.is_file():
        return DEFAULT_COST_CEILING_USD
    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return DEFAULT_COST_CEILING_USD
    if not isinstance(data, dict):
        return DEFAULT_COST_CEILING_USD
    tripwires = data.get("tripwires")
    if not isinstance(tripwires, dict):
        return DEFAULT_COST_CEILING_USD
    extras = tripwires.get("extra") or []
    if not isinstance(extras, list):
        return DEFAULT_COST_CEILING_USD
    for entry in extras:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != CostCeilingTripwire.id:
            continue
        params = entry.get("params") or {}
        if not isinstance(params, dict):
            continue
        ceiling = params.get("ceiling_usd")
        if isinstance(ceiling, (int, float)) and ceiling > 0:
            return float(ceiling)
    return DEFAULT_COST_CEILING_USD


def _marker_substantive(marker_path: Path) -> bool:
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


__all__ = ["DEFAULT_COST_CEILING_USD", "CostCeilingTripwire"]
