"""Unit tests for `core/graph/dependency.py`.

Covers:
- Graph construction from a list of Issues
- Cycle detection: simple cycles, self-loops, disjoint cycles
- Critical path: longest chain through the dependency DAG
- Mermaid and DOT rendering
"""

from __future__ import annotations

from tripwire.core.graph.dependency import (
    build_dependency_graph,
    to_dot,
    to_mermaid,
)
from tripwire.models import Issue


def make_issue(key: str, blocked_by: list[str] | None = None, **kw: object) -> Issue:
    return Issue(
        id=key,
        title=kw.get("title", f"Test {key}"),  # type: ignore[arg-type]
        status=kw.get("status", "todo"),  # type: ignore[arg-type]
        priority="medium",
        executor="ai",
        verifier="required",
        blocked_by=blocked_by or [],
    )


class TestBuildDependencyGraph:
    def test_empty(self) -> None:
        result = build_dependency_graph([])
        assert result.nodes == []
        assert result.edges == []
        assert result.cycles == []
        assert result.critical_path == []

    def test_single_issue(self) -> None:
        result = build_dependency_graph([make_issue("TST-1")])
        assert len(result.nodes) == 1
        assert result.nodes[0].id == "TST-1"
        assert result.edges == []
        assert result.critical_path == ["TST-1"]

    def test_simple_chain(self) -> None:
        issues = [
            make_issue("TST-1"),
            make_issue("TST-2", blocked_by=["TST-1"]),
            make_issue("TST-3", blocked_by=["TST-2"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.nodes) == 3
        assert len(result.edges) == 2
        assert result.cycles == []
        # Critical path walks from deepest blocker (TST-1) to tip (TST-3)
        assert result.critical_path == ["TST-1", "TST-2", "TST-3"]

    def test_unknown_blocker_skipped(self) -> None:
        # Blocker references an issue that isn't in the list; edge should
        # be omitted rather than raising. The validator catches dangling
        # blocked_by refs separately.
        issues = [make_issue("TST-1", blocked_by=["TST-99"])]
        result = build_dependency_graph(issues)
        assert result.edges == []

    def test_branching_graph(self) -> None:
        # TST-4 blocked by TST-2 and TST-3, both of which are blocked by TST-1.
        issues = [
            make_issue("TST-1"),
            make_issue("TST-2", blocked_by=["TST-1"]),
            make_issue("TST-3", blocked_by=["TST-1"]),
            make_issue("TST-4", blocked_by=["TST-2", "TST-3"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.nodes) == 4
        assert len(result.edges) == 4
        assert result.cycles == []
        # Longest path is length 3 (TST-1 → either → TST-4)
        assert len(result.critical_path) == 3
        assert result.critical_path[0] == "TST-1"
        assert result.critical_path[-1] == "TST-4"


class TestCycleDetection:
    def test_self_loop(self) -> None:
        issues = [make_issue("TST-1", blocked_by=["TST-1"])]
        result = build_dependency_graph(issues)
        assert len(result.cycles) == 1
        assert "TST-1" in result.cycles[0]

    def test_two_issue_cycle(self) -> None:
        issues = [
            make_issue("TST-1", blocked_by=["TST-2"]),
            make_issue("TST-2", blocked_by=["TST-1"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.cycles) == 1
        assert set(result.cycles[0]) == {"TST-1", "TST-2"}
        # Cycles prevent critical path computation
        assert result.critical_path == []

    def test_three_issue_cycle(self) -> None:
        issues = [
            make_issue("TST-1", blocked_by=["TST-3"]),
            make_issue("TST-2", blocked_by=["TST-1"]),
            make_issue("TST-3", blocked_by=["TST-2"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.cycles) == 1
        assert set(result.cycles[0]) == {"TST-1", "TST-2", "TST-3"}

    def test_disjoint_cycles(self) -> None:
        issues = [
            make_issue("TST-1", blocked_by=["TST-2"]),
            make_issue("TST-2", blocked_by=["TST-1"]),
            make_issue("TST-3", blocked_by=["TST-4"]),
            make_issue("TST-4", blocked_by=["TST-3"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.cycles) == 2

    def test_cycle_deduplication(self) -> None:
        """A cycle should be reported once regardless of where DFS started."""
        issues = [
            make_issue("TST-1", blocked_by=["TST-2"]),
            make_issue("TST-2", blocked_by=["TST-1"]),
            make_issue("TST-3", blocked_by=["TST-1"]),
        ]
        result = build_dependency_graph(issues)
        assert len(result.cycles) == 1


class TestMermaidRendering:
    def test_basic_mermaid(self) -> None:
        issues = [
            make_issue("TST-1"),
            make_issue("TST-2", blocked_by=["TST-1"]),
        ]
        result = build_dependency_graph(issues)
        output = to_mermaid(result)
        assert output.startswith("graph LR")
        assert "TST-1" in output
        assert "TST-2" in output
        assert "TST-2 --> TST-1" in output

    def test_status_coloring(self) -> None:
        issues = [
            make_issue("TST-1", status="in_progress"),
            make_issue("TST-2", status="done"),
        ]
        result = build_dependency_graph(issues)
        output = to_mermaid(result)
        assert "classDef status_in_progress" in output
        assert "classDef status_done" in output


class TestDotRendering:
    def test_basic_dot(self) -> None:
        issues = [make_issue("TST-1"), make_issue("TST-2", blocked_by=["TST-1"])]
        result = build_dependency_graph(issues)
        output = to_dot(result)
        assert output.startswith("digraph dependencies")
        assert '"TST-2" -> "TST-1"' in output
