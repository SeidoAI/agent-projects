"""Unit tests for the selector grammar and evaluator (F9)."""

from __future__ import annotations

from tripwire.core.selectors import (
    _DOWNSTREAM_RE,
    _TAG_RE,
    _UPSTREAM_RE,
    _bfs,
)


class TestPatterns:
    def test_downstream_simple(self) -> None:
        m = _DOWNSTREAM_RE.match("SEI-42+")
        assert m
        assert m.group(1) == "SEI-42"
        assert m.group(2) == ""

    def test_downstream_with_depth(self) -> None:
        m = _DOWNSTREAM_RE.match("SEI-42+2")
        assert m
        assert m.group(1) == "SEI-42"
        assert m.group(2) == "2"

    def test_upstream(self) -> None:
        m = _UPSTREAM_RE.match("+SEI-42")
        assert m
        assert m.group(1) == "SEI-42"

    def test_tag(self) -> None:
        m = _TAG_RE.match("tag:critical")
        assert m
        assert m.group(1) == "critical"

    def test_plain_id_does_not_match_downstream(self) -> None:
        m = _DOWNSTREAM_RE.match("SEI-42")
        assert m is None

    def test_plain_id_does_not_match_upstream(self) -> None:
        m = _UPSTREAM_RE.match("SEI-42")
        assert m is None


class TestBfs:
    def test_simple_chain(self) -> None:
        adj = {"A": {"B"}, "B": {"C"}}
        assert _bfs("A", adj, None) == {"A", "B", "C"}

    def test_depth_limit(self) -> None:
        adj = {"A": {"B"}, "B": {"C"}, "C": {"D"}}
        assert _bfs("A", adj, 1) == {"A", "B"}

    def test_depth_zero(self) -> None:
        adj = {"A": {"B"}}
        assert _bfs("A", adj, 0) == {"A"}

    def test_cycle_safe(self) -> None:
        adj = {"A": {"B"}, "B": {"A"}}
        assert _bfs("A", adj, None) == {"A", "B"}

    def test_disconnected(self) -> None:
        adj = {"A": {"B"}}
        assert _bfs("C", adj, None) == {"C"}

    def test_branching(self) -> None:
        adj = {"A": {"B", "C"}, "B": {"D"}}
        assert _bfs("A", adj, None) == {"A", "B", "C", "D"}
