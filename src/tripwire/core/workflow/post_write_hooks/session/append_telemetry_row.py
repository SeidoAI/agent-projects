"""Post-write hook: append a routing-telemetry row on session completion."""

from __future__ import annotations

from pathlib import Path

from tripwire.models.session import AgentSession


def append_telemetry_record(project_dir: Path, *, session: AgentSession) -> None:
    """Append a routing-telemetry row. ``close_active_engagement`` must
    run first so ``duration_min`` derives from a closed engagement on
    terminals.

    Exceptions propagate. The executor's wrapper logs and continues.
    """
    from tripwire.core.routing_telemetry import (
        append_telemetry_row,
        build_telemetry_row,
    )
    from tripwire.core.session_cost import compute_session_cost

    cost = compute_session_cost(project_dir, session.id).total_usd
    row = build_telemetry_row(project_dir, session, cost_usd=cost)
    append_telemetry_row(project_dir, row)
