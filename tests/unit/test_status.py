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
        p = make_project({"todo": ["in_progress"], "in_progress": ["done"]})
        assert is_transition_allowed(p, "todo", "in_progress")

    def test_disallowed(self) -> None:
        p = make_project({"todo": ["in_progress"], "in_progress": ["done"]})
        assert not is_transition_allowed(p, "todo", "done")

    def test_self_transition_always_allowed(self) -> None:
        p = make_project({"todo": ["in_progress"]})
        assert is_transition_allowed(p, "todo", "todo")

    def test_unknown_source(self) -> None:
        p = make_project({"todo": ["in_progress"]})
        assert not is_transition_allowed(p, "qa", "done")


class TestReachableStatuses:
    def test_full_seido_default_flow(self) -> None:
        p = make_project(
            {
                "backlog": ["todo", "canceled"],
                "todo": ["in_progress", "backlog", "canceled"],
                "in_progress": ["verifying", "todo", "canceled"],
                "verifying": ["reviewing", "in_progress"],
                "reviewing": ["testing", "in_progress"],
                "testing": ["ready", "reviewing"],
                "ready": ["updating"],
                "updating": ["done"],
                "done": [],
                "canceled": ["backlog"],
            }
        )
        reachable = reachable_statuses(p)
        # Every declared status should be reachable from backlog
        assert reachable == set(p.status_transitions.keys())

    def test_isolated_status_not_reachable(self) -> None:
        p = make_project(
            {
                "backlog": ["todo"],
                "todo": ["done"],
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
        p = make_project({"backlog": ["todo"], "todo": ["done"], "done": []})
        assert is_status_reachable(p, "done")

    def test_unreachable(self) -> None:
        p = make_project(
            {"backlog": ["todo"], "todo": ["done"], "done": [], "orphan": []}
        )
        assert not is_status_reachable(p, "orphan")
