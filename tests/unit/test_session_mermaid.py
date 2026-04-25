"""Tests for the mermaid session-graph generator."""

from __future__ import annotations

from tripwire.core.session_mermaid import (
    UNFINISHED_THRESHOLD,
    SessionForGraph,
    render_session_mermaid,
)


def _s(
    sid: str, status: str = "planned", blocked_by: list[str] | None = None
) -> SessionForGraph:
    return SessionForGraph(id=sid, status=status, blocked_by=blocked_by or [])


# ============================================================================
# Empty / single
# ============================================================================


def test_empty_sessions_returns_placeholder() -> None:
    out = render_session_mermaid([])
    assert out.startswith("graph LR")
    # Empty graphs should still parse on github.com — include a single
    # placeholder node so renderers don't bail.
    assert "no-sessions" in out


def test_single_session_no_edges() -> None:
    out = render_session_mermaid([_s("solo", "planned")])
    assert "graph LR" in out
    assert "solo[" in out
    assert ":::planned" in out
    # No edges
    assert "-->" not in out


# ============================================================================
# Edges
# ============================================================================


def test_edge_from_blocker_to_dependent() -> None:
    out = render_session_mermaid(
        [_s("a", "completed"), _s("b", "planned", blocked_by=["a"])]
    )
    # Edge points from blocker to dependent (a finishes → b unblocks).
    assert "a --> b" in out


def test_dangling_blocker_is_dropped() -> None:
    """Blockers referencing unknown sessions are silently dropped — they're
    surfaced by the validator, not us."""
    out = render_session_mermaid([_s("a", "planned", blocked_by=["ghost"])])
    assert "ghost" not in out
    assert "-->" not in out


# ============================================================================
# Status classDefs
# ============================================================================


def test_class_defs_emitted_for_used_statuses_only() -> None:
    out = render_session_mermaid(
        [
            _s("a", "completed"),
            _s("b", "executing"),
            _s("c", "queued"),
        ]
    )
    # Only status classes that appear should get classDefs (smaller diffs,
    # less mermaid noise).
    assert "classDef completed " in out
    assert "classDef executing " in out
    assert "classDef queued " in out
    assert "classDef paused " not in out
    assert "classDef failed " not in out


def test_unknown_status_falls_back_to_planned() -> None:
    """Unknown statuses (custom enums) get the planned class — readable
    default rather than a silent crash."""
    out = render_session_mermaid([_s("a", "rocketship")])
    assert ":::planned" in out
    assert "classDef planned " in out


def test_node_label_includes_status() -> None:
    out = render_session_mermaid([_s("a", "completed")])
    assert 'a["a<br/>(completed)"]' in out


# ============================================================================
# Determinism
# ============================================================================


def test_topological_sort_with_alpha_tie_break() -> None:
    """Two sessions with the same depth (both roots) emit in alphabetical
    order. Same input → byte-identical output."""
    out = render_session_mermaid(
        [
            _s("zulu", "planned"),
            _s("alpha", "planned"),
            _s("mike", "planned", blocked_by=["alpha"]),
        ]
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    # alpha and zulu are roots; alpha emits first (alphabetical tie-break).
    alpha_idx = next(i for i, line in enumerate(lines) if line.startswith("alpha["))
    zulu_idx = next(i for i, line in enumerate(lines) if line.startswith("zulu["))
    mike_idx = next(i for i, line in enumerate(lines) if line.startswith("mike["))
    assert alpha_idx < zulu_idx
    assert alpha_idx < mike_idx  # mike depends on alpha


def test_input_order_does_not_change_output() -> None:
    sessions_a = [
        _s("zulu", "planned"),
        _s("alpha", "planned"),
        _s("mike", "planned", blocked_by=["alpha"]),
    ]
    sessions_b = [
        _s("mike", "planned", blocked_by=["alpha"]),
        _s("alpha", "planned"),
        _s("zulu", "planned"),
    ]
    assert render_session_mermaid(sessions_a) == render_session_mermaid(sessions_b)


# ============================================================================
# Truncation
# ============================================================================


def test_under_threshold_renders_full_graph() -> None:
    sessions = [_s(f"s{i:02d}", "completed") for i in range(UNFINISHED_THRESHOLD)]
    out = render_session_mermaid(sessions)
    # All sessions present.
    for i in range(UNFINISHED_THRESHOLD):
        assert f"s{i:02d}[" in out
    # No truncation note.
    assert "complete" not in out.split("classDef")[0] or "complete (showing" not in out


def test_over_threshold_renders_unfinished_only_with_complete_note() -> None:
    completed = [_s(f"done{i:02d}", "completed") for i in range(UNFINISHED_THRESHOLD)]
    unfinished = [_s("active1", "executing"), _s("planned1", "planned")]
    out = render_session_mermaid(completed + unfinished)
    # Unfinished sessions present.
    assert "active1[" in out
    assert "planned1[" in out
    # Completed sessions omitted from the graph nodes.
    assert "done00[" not in out
    # Note tells the reader N completed sessions exist.
    assert f"{UNFINISHED_THRESHOLD}" in out
    assert "complete" in out


def test_over_threshold_drops_edges_to_completed_blockers() -> None:
    completed = [_s(f"done{i:02d}", "completed") for i in range(UNFINISHED_THRESHOLD)]
    # planned1 is blocked by done00 — that edge would point at a node that
    # got truncated, so it must be dropped (or pointed at the note).
    unfinished = [_s("planned1", "planned", blocked_by=["done00"])]
    out = render_session_mermaid(completed + unfinished)
    assert "done00 --> planned1" not in out


# ============================================================================
# AgentSession integration
# ============================================================================


def test_accepts_agent_session_objects(tmp_path_project, save_test_session) -> None:
    """The generator should accept real AgentSession objects (or any object
    with id/status/blocked_by_sessions), not just our test dataclass."""
    save_test_session(tmp_path_project, "a", status="completed")
    save_test_session(
        tmp_path_project, "b", status="planned", blocked_by_sessions=["a"]
    )
    from tripwire.core.session_store import list_sessions

    sessions = list_sessions(tmp_path_project)
    out = render_session_mermaid(sessions)
    assert "a[" in out
    assert "b[" in out
    assert "a --> b" in out
