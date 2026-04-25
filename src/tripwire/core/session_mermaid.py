"""Mermaid `graph LR` generator for the session DAG.

GitHub renders mermaid in fenced code blocks natively, so the README can
ship a live diagram with no SVG generation and no committed binary
assets. This module turns a list of sessions (each with an id, a status,
and a `blocked_by` list) into a deterministic mermaid block.

Determinism matters here. The block goes into README.md, which CD
re-renders on every push to main. Non-deterministic ordering would
produce spurious diffs and trigger pointless commits. We sort topologically
with an alphabetical tie-break, and only emit `classDef` lines for status
classes actually used.

Truncation: very large graphs render slowly on github.com. When the
total session count exceeds `UNFINISHED_THRESHOLD`, we render only the
unfinished sub-graph and add a single note saying "N sessions complete".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# When the session count exceeds this, render only the unfinished sub-graph
# plus a "✓ N complete" note. Tunable via the renderer kwarg.
UNFINISHED_THRESHOLD = 30

# Sessions in these statuses are treated as "finished" for truncation
# purposes. `done` and `completed` are both terminal in the project enums;
# `abandoned` is the explicit cancel terminal.
_FINISHED_STATUSES: frozenset[str] = frozenset({"completed", "done", "abandoned"})

# Status → mermaid classDef line. Colours chosen for github light + dark
# themes; the `color:` attribute keeps text legible on both. Only the
# classes actually referenced in a given graph get emitted.
_CLASS_DEFS: dict[str, str] = {
    "planned": "fill:#e0e0e0,stroke:#999,color:#333",
    "queued": "fill:#fff3b0,stroke:#cc9933,color:#333",
    "executing": "fill:#cfe9ff,stroke:#3399cc,color:#333",
    "active": "fill:#cfe9ff,stroke:#3399cc,color:#333",
    "paused": "fill:#ffe0cc,stroke:#cc6633,color:#333",
    "failed": "fill:#ffcccc,stroke:#cc3333,color:#333",
    "abandoned": "fill:#ffcccc,stroke:#cc3333,color:#333",
    "waiting_for_ci": "fill:#fff3b0,stroke:#cc9933,color:#333",
    "waiting_for_review": "fill:#fff3b0,stroke:#cc9933,color:#333",
    "waiting_for_deploy": "fill:#fff3b0,stroke:#cc9933,color:#333",
    "re_engaged": "fill:#ffe0cc,stroke:#cc6633,color:#333",
    "completed": "fill:#d4ffd4,stroke:#33aa33,color:#333",
    "done": "fill:#9fdf9f,stroke:#005500,color:#000",
}

# Statuses we don't recognise fall back to this class. Better than crashing
# on a custom session_status enum.
_FALLBACK_CLASS = "planned"


@runtime_checkable
class _SessionLike(Protocol):
    """Anything with id/status/blocked_by_sessions can be graphed.

    Both AgentSession (model) and SessionForGraph (test dataclass) satisfy
    this. Plain dicts go through `_normalise` instead.
    """

    id: str
    status: str
    blocked_by_sessions: list[str]


@dataclass
class SessionForGraph:
    """Lightweight test/in-memory shape — same fields as AgentSession needs."""

    id: str
    status: str
    blocked_by: list[str] = field(default_factory=list)


def _normalise(session: Any) -> SessionForGraph:
    """Coerce AgentSession / dict / SessionForGraph to SessionForGraph."""
    if isinstance(session, SessionForGraph):
        return session
    # AgentSession: blocked_by lives on `blocked_by_sessions`.
    blocked_by_sessions = getattr(session, "blocked_by_sessions", None)
    if blocked_by_sessions is not None:
        return SessionForGraph(
            id=session.id,
            status=session.status,
            blocked_by=list(blocked_by_sessions),
        )
    # dict path.
    if isinstance(session, dict):
        return SessionForGraph(
            id=session["id"],
            status=session["status"],
            blocked_by=list(
                session.get("blocked_by_sessions") or session.get("blocked_by") or []
            ),
        )
    raise TypeError(f"Cannot graph session of type {type(session).__name__}")


def _topo_sort_alpha(by_id: dict[str, SessionForGraph]) -> list[str]:
    """Topological sort with alphabetical tie-break.

    Roots first (sessions with no blockers), then everything reachable by
    following dependents, with ties broken alphabetically. Cycles aren't
    expected here — the validator catches them — but if one slips through
    we fall back to alphabetical order over the unsorted remainder so the
    output is still deterministic.
    """
    in_degree: dict[str, int] = dict.fromkeys(by_id, 0)
    for s in by_id.values():
        for dep in s.blocked_by:
            if dep in by_id:
                in_degree[s.id] += 1

    # Roots are sessions with in-degree 0. Process them in alpha order.
    ready = sorted(sid for sid, deg in in_degree.items() if deg == 0)
    order: list[str] = []
    while ready:
        sid = ready.pop(0)
        order.append(sid)
        # Find dependents of sid (sessions whose blocked_by contains sid).
        new_ready: list[str] = []
        for other in by_id.values():
            if (
                sid in other.blocked_by
                and other.id not in order
                and other.id not in ready
            ):
                in_degree[other.id] -= 1
                if in_degree[other.id] == 0:
                    new_ready.append(other.id)
        # Re-sort the queue after each pop so alpha order holds across rounds.
        ready = sorted(set(ready) | set(new_ready))

    # If a cycle dropped sessions, append them in alpha order so the output
    # is still complete and deterministic.
    if len(order) < len(by_id):
        leftover = sorted(set(by_id) - set(order))
        order.extend(leftover)
    return order


def _class_for(status: str) -> str:
    """Mermaid class name for a status, falling back if unknown."""
    return status if status in _CLASS_DEFS else _FALLBACK_CLASS


def render_session_mermaid(
    sessions: list[Any],
    *,
    max_unfinished: int = UNFINISHED_THRESHOLD,
) -> str:
    """Render a `graph LR` mermaid block from a list of sessions.

    Args:
        sessions: AgentSession objects, dicts, or SessionForGraph. Each must
            expose an id, a status, and a list of blocker session ids.
        max_unfinished: When the total session count exceeds this, render
            only the unfinished sub-graph and add a "N complete" note.

    Returns:
        A mermaid block (no surrounding fence). The caller wraps in
        ```` ```mermaid … ``` ```` for markdown.
    """
    normed = [_normalise(s) for s in sessions]

    if not normed:
        # Empty graph — emit a placeholder so the mermaid block renders
        # rather than failing parse on github.com.
        return "\n".join(
            [
                "graph LR",
                '  no-sessions["(no sessions yet)"]:::planned',
                f"  classDef planned {_CLASS_DEFS['planned']}",
            ]
        )

    by_id = {s.id: s for s in normed}

    # Decide whether to truncate.
    truncated = len(normed) > max_unfinished
    completed_count = 0
    if truncated:
        completed_ids = {
            sid for sid, s in by_id.items() if s.status in _FINISHED_STATUSES
        }
        completed_count = len(completed_ids)
        # Drop completed nodes; rewrite blocked_by to drop refs to them.
        kept = {
            sid: SessionForGraph(
                id=s.id,
                status=s.status,
                blocked_by=[b for b in s.blocked_by if b not in completed_ids],
            )
            for sid, s in by_id.items()
            if sid not in completed_ids
        }
        by_id = kept

    if not by_id:
        # All sessions were truncated (everything's done).
        return "\n".join(
            [
                "graph LR",
                f'  all-done["✓ {completed_count} sessions complete"]:::done',
                f"  classDef done {_CLASS_DEFS['done']}",
            ]
        )

    order = _topo_sort_alpha(by_id)

    lines: list[str] = ["graph LR"]
    used_classes: set[str] = set()

    # Node declarations in topo order. `name<br/>(status)` keeps the status
    # visible without clicking — important when the graph carries the
    # at-a-glance signal.
    for sid in order:
        s = by_id[sid]
        cls = _class_for(s.status)
        used_classes.add(cls)
        lines.append(f'  {sid}["{sid}<br/>({s.status})"]:::{cls}')

    # Edges in (source, target) lexicographic order for deterministic diffs.
    edges: list[tuple[str, str]] = []
    for s in by_id.values():
        for dep in s.blocked_by:
            if dep in by_id:
                edges.append((dep, s.id))
    for src, tgt in sorted(edges):
        lines.append(f"  {src} --> {tgt}")

    if truncated and completed_count:
        # Single annotation node — not connected to anything to avoid edge
        # density. The `done` class signals "this is finished work".
        lines.append(f'  done-summary["✓ {completed_count} sessions complete"]:::done')
        used_classes.add("done")

    # ClassDefs only for classes actually used. Sorted for diff stability.
    for cls in sorted(used_classes):
        lines.append(f"  classDef {cls} {_CLASS_DEFS[cls]}")

    return "\n".join(lines)
