"""Tests for ``task_kind`` integration into spawn config (KUI-92 §3.A2).

A session declares ``task_kind`` in ``spawn_config``. The resolved value
flows two ways:

1. Into ``build_claude_args`` so the spawned agent runs on the route's
   ``(model, effort)`` rather than the default ``(opus, xhigh)``.
2. Into ``tripwire session show`` so a human can confirm the route
   before launch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.spawn_config import build_claude_args
from tripwire.core.spawn_routing import resolve_route
from tripwire.models.spawn import SpawnConfigValues, SpawnDefaults


def test_spawn_config_values_has_task_kind_field() -> None:
    """``SpawnConfigValues`` must include a ``task_kind`` (default empty)."""
    cfg = SpawnConfigValues()
    assert hasattr(cfg, "task_kind")
    assert cfg.task_kind == ""


def test_spawn_config_values_accepts_task_kind() -> None:
    """The ``task_kind`` field must be assignable from session.yaml input."""
    cfg = SpawnConfigValues(task_kind="lint_or_template_edit")
    assert cfg.task_kind == "lint_or_template_edit"


def test_build_claude_args_uses_route_when_provided(tmp_path: Path) -> None:
    """A non-empty ``task_kind`` causes ``build_claude_args`` to substitute
    the route's model+effort for the cfg defaults."""
    defaults = SpawnDefaults.model_validate({"config": {"task_kind": "lint_or_template_edit"}})
    args = build_claude_args(
        defaults,
        prompt="x",
        system_append="y",
        session_id="s1",
        claude_session_id="abc",
        resume=False,
        project_dir=tmp_path,
    )
    # Route is (claude, sonnet, low) for lint_or_template_edit.
    assert "--model" in args
    assert args[args.index("--model") + 1] == "sonnet"
    assert "--effort" in args
    assert args[args.index("--effort") + 1] == "low"


def test_build_claude_args_empty_task_kind_uses_cfg_defaults(tmp_path: Path) -> None:
    """Empty ``task_kind`` falls back to the route default (agentic_loop).

    The default route (agentic_loop) is (opus, xhigh) — same as the
    cfg defaults ship today. Either path lands at (opus, xhigh).
    """
    defaults = SpawnDefaults.model_validate({})
    args = build_claude_args(
        defaults,
        prompt="x",
        system_append="y",
        session_id="s1",
        claude_session_id="abc",
        resume=False,
        project_dir=tmp_path,
    )
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--effort") + 1] == "xhigh"


def test_build_claude_args_unknown_task_kind_raises(tmp_path: Path) -> None:
    """An unknown ``task_kind`` propagates ``UnknownTaskKindError``."""
    from tripwire.core.spawn_routing import UnknownTaskKindError

    defaults = SpawnDefaults.model_validate({"config": {"task_kind": "not_a_kind"}})
    with pytest.raises(UnknownTaskKindError):
        build_claude_args(
            defaults,
            prompt="x",
            system_append="y",
            session_id="s1",
            claude_session_id="abc",
            resume=False,
            project_dir=tmp_path,
        )


def test_resolve_route_for_session_show_returns_tuple(tmp_path: Path) -> None:
    """``session show`` reads ``(provider, model, effort)`` from the route."""
    route = resolve_route("gnarly_debug", tmp_path)
    assert (route.provider, route.model, route.effort) == ("claude", "opus", "max")


def test_session_show_renders_resolved_route(save_test_session, tmp_path_project) -> None:
    """``tripwire session show`` text output contains a ``Routing:`` block
    naming the resolved provider, model, and effort for the session."""
    from click.testing import CliRunner

    from tripwire.cli.session import session_cmd

    save_test_session(
        tmp_path_project,
        session_id="session-route-show",
        spawn_config={"config": {"task_kind": "lint_or_template_edit"}},
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "show",
            "session-route-show",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Routing:" in result.output
    assert "lint_or_template_edit" in result.output
    assert "claude" in result.output
    assert "sonnet" in result.output
    assert "low" in result.output


def test_session_show_renders_default_route_when_task_kind_empty(
    save_test_session, tmp_path_project
) -> None:
    """When ``task_kind`` is empty, ``session show`` must still render the
    Routing block, naming the default route (agentic_loop)."""
    from click.testing import CliRunner

    from tripwire.cli.session import session_cmd

    save_test_session(tmp_path_project, session_id="session-default-route")

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "show",
            "session-default-route",
            "--project-dir",
            str(tmp_path_project),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Routing:" in result.output
    assert "agentic_loop" in result.output
