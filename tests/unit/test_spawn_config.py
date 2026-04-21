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
        claude_session_id="abc-123",
        resume=False,
    )
    assert args[0] == "claude"
    assert "-p" in args
    assert "Do the thing." in args
    assert "--session-id" in args
    assert "abc-123" in args
    assert "--model" in args
    assert "--disallowedTools" in args
    assert "Agent" in args
    assert "--resume" not in args


def test_build_claude_args_with_resume():
    from tripwire.models.spawn import SpawnDefaults

    defaults = SpawnDefaults.model_validate({})
    args = build_claude_args(
        defaults,
        prompt="x",
        system_append="y",
        claude_session_id="abc",
        resume=True,
    )
    assert args[-1] == "--resume"
