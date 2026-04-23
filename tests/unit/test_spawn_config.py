"""Spawn config resolver: precedence + arg building."""

from pathlib import Path

import yaml

from tripwire.core.session_store import load_session
from tripwire.core.spawn_config import (
    _deep_merge,
    build_claude_args,
    load_resolved_spawn_config,
    render_prompt,
)


def test_deep_merge_basic():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    override = {"b": {"y": 20, "z": 30}}
    merged = _deep_merge(base, override)
    assert merged == {"a": 1, "b": {"x": 1, "y": 20, "z": 30}}


def test_deep_merge_lists_replaced():
    base = {"items": [1, 2, 3]}
    override = {"items": [4]}
    merged = _deep_merge(base, override)
    assert merged == {"items": [4]}


def test_default_resolves_from_shipped(tmp_path_project: Path):
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.model == "opus"
    assert resolved.config.max_budget_usd == 50


def test_project_inline_override_wins_over_default(tmp_path_project: Path):
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"] = {"config": {"max_budget_usd": 100}}
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.max_budget_usd == 100
    # Other defaults preserved.
    assert resolved.config.model == "opus"


def test_project_file_override_read(tmp_path_project: Path):
    override_dir = tmp_path_project / ".tripwire" / "spawn"
    override_dir.mkdir(parents=True)
    override_dir.joinpath("defaults.yaml").write_text(
        "config:\n  model: haiku\n", encoding="utf-8"
    )

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.model == "haiku"


def test_session_override_wins_over_project(tmp_path_project: Path, save_test_session):
    # Project sets model=haiku, session sets model=sonnet → sonnet wins.
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"] = {"config": {"model": "haiku"}}
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    save_test_session(
        tmp_path_project,
        "s1",
        spawn_config={"config": {"model": "sonnet"}},
    )
    session = load_session(tmp_path_project, "s1")
    resolved = load_resolved_spawn_config(tmp_path_project, session=session)
    assert resolved.config.model == "sonnet"


def test_render_prompt_substitutes_placeholders():
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate(
        {"prompt_template": "hello {name} on {session_id}"}
    )
    rendered = render_prompt(defaults, name="agent", session_id="s1")
    assert rendered == "hello agent on s1"


def test_build_claude_args_shape():
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate({})
    args = build_claude_args(
        defaults,
        prompt="Do the thing.",
        system_append="extras",
        session_id="my-session",
        claude_session_id="abc-123",
        resume=False,
    )
    assert args[0] == "claude"
    assert "-p" in args
    assert "Do the thing." in args
    # Both session identifiers present with their respective flags.
    assert "--name" in args
    assert "my-session" in args
    assert "--session-id" in args
    assert "abc-123" in args
    # All spec §8.1 flags emitted.
    assert "--effort" in args
    assert "--max-budget-usd" in args
    assert "50" in args  # default max_budget_usd
    assert "--model" in args
    assert "--fallback-model" in args
    assert "--permission-mode" in args
    assert "--disallowedTools" in args
    # disallowed_tools is joined comma-separated; the value arg contains
    # each disallowed tool name.
    disallowed_value = args[args.index("--disallowedTools") + 1]
    assert "Agent" in disallowed_value
    assert "--max-turns" in args
    assert "--output-format" in args
    assert "--append-system-prompt" in args
    assert "--resume" not in args


def test_build_claude_args_with_resume():
    """resume=True: --resume <uuid> is emitted, --session-id is NOT
    (claude rejects the combination without --fork-session)."""
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate({})
    args = build_claude_args(
        defaults,
        prompt="x",
        system_append="y",
        session_id="s1",
        claude_session_id="abc",
        resume=True,
    )
    assert "--resume" in args
    resume_idx = args.index("--resume")
    assert args[resume_idx + 1] == "abc"
    assert "--session-id" not in args
    # --name still present (display-only, safe with --resume).
    assert "--name" in args


def test_build_claude_args_resume_false_uses_session_id():
    """resume=False: --session-id <uuid> is emitted, --resume is NOT."""
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate({})
    args = build_claude_args(
        defaults,
        prompt="x",
        system_append="y",
        session_id="s1",
        claude_session_id="abc",
        resume=False,
    )
    assert "--session-id" in args
    assert args[args.index("--session-id") + 1] == "abc"
    assert "--resume" not in args


# -------- runtime field (T1) --------


def test_runtime_defaults_to_subprocess(tmp_path_project):
    resolved = load_resolved_spawn_config(tmp_path_project)
    assert resolved.invocation.runtime == "subprocess"


def test_runtime_session_override_beats_default(
    tmp_path_project, save_test_session
):
    save_test_session(
        tmp_path_project,
        "s1",
        status="planned",
        spawn_config={"invocation": {"runtime": "manual"}},
    )

    session = load_session(tmp_path_project, "s1")
    resolved = load_resolved_spawn_config(tmp_path_project, session=session)
    assert resolved.invocation.runtime == "manual"


def test_runtime_rejects_unknown_value(tmp_path_project, save_test_session):
    import pytest
    from pydantic import ValidationError

    save_test_session(
        tmp_path_project,
        "s1",
        status="planned",
        spawn_config={"invocation": {"runtime": "tmux"}},
    )

    session = load_session(tmp_path_project, "s1")
    with pytest.raises(ValidationError):
        load_resolved_spawn_config(tmp_path_project, session=session)


def test_resume_prompt_template_shipped_default(tmp_path_project):
    """The shipped defaults.yaml ships a non-empty resume prompt template."""
    resolved = load_resolved_spawn_config(tmp_path_project)
    assert resolved.resume_prompt_template.strip()
    assert "Resuming session" in resolved.resume_prompt_template


def test_disallowed_tools_includes_ask_and_send_user_message(tmp_path_project):
    """Defaults block AskUserQuestion and SendUserMessage to prevent
    retry-loops in -p mode (see probe 1 in the session design)."""
    resolved = load_resolved_spawn_config(tmp_path_project)
    assert "AskUserQuestion" in resolved.config.disallowed_tools
    assert "SendUserMessage" in resolved.config.disallowed_tools
    assert "Agent" in resolved.config.disallowed_tools


def test_render_resume_prompt_interpolates():
    from tripwire.core.spawn_config import render_resume_prompt
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate(
        {"resume_prompt_template": "Resuming {session_id} at {plan_path}"}
    )
    out = render_resume_prompt(defaults, session_id="s1", plan_path="/tmp/x")
    assert out == "Resuming s1 at /tmp/x"
