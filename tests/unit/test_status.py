"""Unit tests for `core/status.py` (status transition validation)."""

from __future__ import annotations

from tripwire.core.status import (
    is_status_reachable,
    is_transition_allowed,
    reachable_statuses,
)
from tripwire.models import ProjectConfig


def make_project(transitions: dict[str, list[str]]) -> ProjectConfig:
    return ProjectConfig(
        name="t",
        key_prefix="T",
        statuses=list(transitions.keys()),
        status_transitions=transitions,
    )


class TestIsTransitionAllowed:
    def test_allowed(self) -> None:
        p = make_project({"queued": ["executing"], "executing": ["done"]})
        assert is_transition_allowed(p, "queued", "executing")

    def test_disallowed(self) -> None:
        p = make_project({"queued": ["executing"], "executing": ["done"]})
        assert not is_transition_allowed(p, "queued", "done")

    def test_self_transition_always_allowed(self) -> None:
        p = make_project({"queued": ["executing"]})
        assert is_transition_allowed(p, "queued", "queued")

    def test_unknown_source(self) -> None:
        p = make_project({"queued": ["executing"]})
        assert not is_transition_allowed(p, "qa", "done")


class TestReachableStatuses:
    def test_full_seido_default_flow(self) -> None:
        p = make_project(
            {
                "planned": ["queued", "abandoned"],
                "queued": ["executing", "planned", "abandoned"],
                "executing": ["in_review", "queued", "abandoned"],
                "in_review": ["verified", "executing"],
                "verified": ["done", "in_review"],
                "done": [],
                "abandoned": ["planned"],
            }
        )
        reachable = reachable_statuses(p)
        # Every declared status should be reachable from backlog
        assert reachable == set(p.status_transitions.keys())

    def test_isolated_status_not_reachable(self) -> None:
        p = make_project(
            {
                "planned": ["queued"],
                "queued": ["done"],
                "done": [],
                "orphan": [],
            }
        )
        reachable = reachable_statuses(p)
        assert "orphan" not in reachable
        assert "done" in reachable

    def test_no_transitions_returns_all_statuses(self) -> None:
        p = ProjectConfig(name="t", key_prefix="T", statuses=["a", "b", "c"])
        reachable = reachable_statuses(p)
        assert reachable == {"a", "b", "c"}


class TestIsStatusReachable:
    def test_reachable(self) -> None:
        p = make_project({"planned": ["queued"], "queued": ["done"], "done": []})
        assert is_status_reachable(p, "done")

    def test_unreachable(self) -> None:
        p = make_project(
            {"planned": ["queued"], "queued": ["done"], "done": [], "orphan": []}
        )
        assert not is_status_reachable(p, "orphan")
