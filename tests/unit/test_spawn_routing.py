"""Tests for `tripwire.core.spawn_routing` (KUI-92 v0.7.10 §3.A1).

Routing maps a session's ``task_kind`` to a ``(provider, model, effort)``
tuple. Three layers, highest wins:

1. Project override at ``<project_dir>/.tripwire/spawn/routing.yaml``
2. Shipped default at ``src/tripwire/templates/spawn/routing.yaml``

The session's ``task_kind`` is the lookup key; missing/empty key falls
back to the ``default:`` route declared in the shipped file.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tripwire.core.spawn_routing import (
    RouteResolution,
    UnknownTaskKindError,
    resolve_route,
    shipped_routing_path,
)


def test_shipped_routing_yaml_exists() -> None:
    """The shipped routing.yaml must be present in the package."""
    assert shipped_routing_path().is_file()


@pytest.mark.parametrize(
    "task_kind, expected_model_substr, expected_effort",
    [
        ("lint_or_template_edit", "sonnet", "low"),
        ("small_cli_command", "sonnet", "medium"),
        ("refactor_with_tdd", "sonnet", "high"),
        ("agentic_loop", "opus", "xhigh"),
        ("gnarly_debug", "opus", "max"),
        ("cross_review", "opus", "high"),
    ],
)
def test_resolve_each_known_task_kind_against_shipped(
    tmp_path: Path,
    task_kind: str,
    expected_model_substr: str,
    expected_effort: str,
) -> None:
    """Every documented task_kind resolves against the shipped routing.yaml."""
    route = resolve_route(task_kind, tmp_path)
    assert isinstance(route, RouteResolution)
    assert route.provider == "claude"
    assert expected_model_substr in route.model
    assert route.effort == expected_effort
    assert route.task_kind == task_kind


def test_empty_task_kind_falls_back_to_default(tmp_path: Path) -> None:
    """Empty string => use the ``default:`` route from the shipped file."""
    route = resolve_route("", tmp_path)
    # Spec ships agentic_loop as the default.
    assert route.task_kind == "agentic_loop"
    assert route.provider == "claude"


def test_unknown_task_kind_raises(tmp_path: Path) -> None:
    """Non-empty task_kind that doesn't appear in any layer is an error.

    Silent fallback hides typos; the spec is explicit about the route
    set, so a missing kind is a bug in the session.yaml, not a route.
    """
    with pytest.raises(UnknownTaskKindError):
        resolve_route("not_a_real_kind", tmp_path)


def test_project_override_replaces_route(tmp_path: Path) -> None:
    """Project-level routing.yaml replaces a shipped route entry."""
    override_dir = tmp_path / ".tripwire" / "spawn"
    override_dir.mkdir(parents=True)
    (override_dir / "routing.yaml").write_text(
        textwrap.dedent(
            """\
            routes:
              lint_or_template_edit:
                provider: claude
                model: haiku
                effort: low
            """
        ),
        encoding="utf-8",
    )
    route = resolve_route("lint_or_template_edit", tmp_path)
    assert route.model == "haiku"
    assert route.provider == "claude"
    assert route.effort == "low"


def test_project_override_can_change_default(tmp_path: Path) -> None:
    """Project-level routing.yaml can change which route is the default."""
    override_dir = tmp_path / ".tripwire" / "spawn"
    override_dir.mkdir(parents=True)
    (override_dir / "routing.yaml").write_text(
        textwrap.dedent(
            """\
            default: gnarly_debug
            """
        ),
        encoding="utf-8",
    )
    route = resolve_route("", tmp_path)
    assert route.task_kind == "gnarly_debug"


def test_project_override_can_add_new_route(tmp_path: Path) -> None:
    """Project-level file can declare a route that the shipped file lacks."""
    override_dir = tmp_path / ".tripwire" / "spawn"
    override_dir.mkdir(parents=True)
    (override_dir / "routing.yaml").write_text(
        textwrap.dedent(
            """\
            routes:
              local_only:
                provider: claude
                model: sonnet
                effort: medium
            """
        ),
        encoding="utf-8",
    )
    route = resolve_route("local_only", tmp_path)
    assert route.model == "sonnet"
    assert route.effort == "medium"
