"""Session agenda: DAG computation, launchable resolution, critical path."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


class CycleDetectedError(Exception):
    pass


@dataclass
class SessionInfo:
    id: str
    status: str
    blocked_by: list[str]
    dependents: list[str] = field(default_factory=list)
    is_launchable: bool = False
    critical_path_position: int | None = None


@dataclass
class Recommendation:
    session_id: str
    rank: int
    rationale: str


@dataclass
class AgendaReport:
    totals: dict[str, int] = field(default_factory=dict)
    launchable: list[SessionInfo] = field(default_factory=list)
    blocked: list[SessionInfo] = field(default_factory=list)
    in_flight: list[SessionInfo] = field(default_factory=list)
    completed_sessions: list[SessionInfo] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    all_completed: bool = False


LAUNCHABLE_STATUSES = {"planned", "queued"}
IN_FLIGHT_STATUSES = {"executing", "active", "paused"}
TERMINAL_STATUSES = {"completed", "abandoned"}
COMPLETED_STATUS = "completed"


def build_agenda(sessions: list[dict]) -> AgendaReport:
    """Build an agenda report from a list of session dicts.

    Each dict must have: id, status, blocked_by_sessions.
    """
    report = AgendaReport()
    if not sessions:
        return report

    # Index sessions
    by_id: dict[str, SessionInfo] = {}
    for s in sessions:
        info = SessionInfo(
            id=s["id"],
            status=s["status"],
            blocked_by=list(s.get("blocked_by_sessions") or []),
        )
        by_id[info.id] = info

    # Build adjacency + dependents, resolve orphan blockers
    for info in by_id.values():
        resolved_blockers = []
        for dep_id in info.blocked_by:
            if dep_id not in by_id:
                report.warnings.append(
                    f"Session '{info.id}' blocked by unknown session '{dep_id}'"
                )
                continue
            resolved_blockers.append(dep_id)
            by_id[dep_id].dependents.append(info.id)
        info.blocked_by = resolved_blockers

    # Cycle detection via topological sort (Kahn's algorithm)
    in_degree: dict[str, int] = dict.fromkeys(by_id, 0)
    for info in by_id.values():
        for _dep_id in info.blocked_by:
            in_degree[info.id] += 1

    queue: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
    topo_order: list[str] = []

    while queue:
        sid = queue.pop(0)
        topo_order.append(sid)
        for dep_id in by_id[sid].dependents:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(topo_order) != len(by_id):
        remaining = set(by_id.keys()) - set(topo_order)
        raise CycleDetectedError(
            f"Cycle detected among sessions: {', '.join(sorted(remaining))}"
        )

    # Resolve launchable
    for info in by_id.values():
        all_blockers_done = all(
            by_id[dep_id].status == COMPLETED_STATUS for dep_id in info.blocked_by
        )
        if info.status in LAUNCHABLE_STATUSES and all_blockers_done:
            info.is_launchable = True
            report.launchable.append(info)
        elif info.status in IN_FLIGHT_STATUSES:
            report.in_flight.append(info)
        elif info.status in TERMINAL_STATUSES:
            report.completed_sessions.append(info)
        else:
            report.blocked.append(info)

    # Critical path (longest path in DAG)
    dist: dict[str, int] = dict.fromkeys(by_id, 0)
    pred: dict[str, str | None] = dict.fromkeys(by_id, None)

    for sid in topo_order:
        for dep_id in by_id[sid].dependents:
            if dist[sid] + 1 > dist[dep_id]:
                dist[dep_id] = dist[sid] + 1
                pred[dep_id] = sid

    if dist:
        end = max(dist, key=lambda s: dist[s])
        path: list[str] = []
        current: str | None = end
        while current is not None:
            path.append(current)
            current = pred[current]
        report.critical_path = list(reversed(path))

        for i, sid in enumerate(report.critical_path):
            by_id[sid].critical_path_position = i + 1

    # Recommendations (launchable sessions ranked by blast radius)
    def _blast_radius(sid: str) -> int:
        visited: set[str] = set()
        stack = [sid]
        while stack:
            current = stack.pop()
            for dep in by_id[current].dependents:
                if dep not in visited:
                    visited.add(dep)
                    stack.append(dep)
        return len(visited)

    ranked = sorted(
        report.launchable,
        key=lambda info: _blast_radius(info.id),
        reverse=True,
    )
    for i, info in enumerate(ranked[:5]):
        radius = _blast_radius(info.id)
        on_cp = info.id in report.critical_path
        parts = []
        if radius > 0:
            parts.append(f"unblocks {radius}")
        if on_cp:
            parts.append("on critical path")
        report.recommendations.append(
            Recommendation(
                session_id=info.id,
                rank=i + 1,
                rationale=", ".join(parts) if parts else "no dependents",
            )
        )

    # Totals
    status_counts: dict[str, int] = defaultdict(int)
    for info in by_id.values():
        status_counts[info.status] += 1
    report.totals = dict(status_counts)

    report.all_completed = all(
        info.status in TERMINAL_STATUSES for info in by_id.values()
    )

    return report
