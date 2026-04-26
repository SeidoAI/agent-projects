"""Agent yaml ``runtime`` field is honoured at spawn time (KUI-94 C4).

The agent template at ``agents/<agent_id>.yaml`` may declare
``runtime: claude`` or ``runtime: codex``. When the session's spawn
config doesn't pin ``invocation.runtime`` itself, the agent's
declared runtime is used; this is the per-agent override the spec
calls for.

Resolution ordering: session.spawn_config > project layers > agent
yaml > shipped default. The agent-yaml step is wired up via the new
``_apply_agent_yaml_overrides`` helper consumed by
``runtimes.prep.run_session_prep``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.spawn_config import (
    _apply_agent_yaml_overrides,
    load_resolved_spawn_config,
)
from tripwire.runtimes import get_runtime
from tripwire.runtimes.codex import CodexRuntime


def _write_agent_yaml(project_dir: Path, agent_id: str, body: dict) -> None:
    agents_dir = project_dir / "agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / f"{agent_id}.yaml").write_text(
        yaml.safe_dump(body), encoding="utf-8"
    )


def test_agent_yaml_runtime_codex_resolves_to_codex_runtime(tmp_path_project: Path):
    """Agent yaml says runtime: codex → resolved invocation.runtime
    becomes 'codex' AND provider becomes 'codex' (the two axes
    co-vary by default — explicit values still win)."""
    _write_agent_yaml(
        tmp_path_project,
        "reviewer",
        {
            "id": "reviewer",
            "name": "Reviewer",
            "runtime": "codex",
        },
    )

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(resolved, tmp_path_project, agent_id="reviewer")

    assert resolved.invocation.runtime == "codex"
    assert resolved.config.provider == "codex"
    assert isinstance(get_runtime(resolved.invocation.runtime), CodexRuntime)


def test_agent_yaml_runtime_claude_keeps_claude_runtime(tmp_path_project: Path):
    """Default agent yaml runtime: claude — no change from the shipped
    default; just make sure the helper doesn't accidentally flip
    other settings."""
    _write_agent_yaml(
        tmp_path_project,
        "coder",
        {"id": "coder", "name": "Coder", "runtime": "claude"},
    )

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(resolved, tmp_path_project, agent_id="coder")

    assert resolved.invocation.runtime == "claude"
    assert resolved.config.provider == "claude"


def test_agent_yaml_missing_is_a_noop(tmp_path_project: Path):
    """Agent yaml file may be absent (e.g. tests that don't materialise
    one); the override step must be tolerant — leave resolved config
    untouched."""
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(
        resolved, tmp_path_project, agent_id="not-a-real-agent"
    )
    assert resolved.invocation.runtime == "claude"
    assert resolved.config.provider == "claude"


def test_agent_yaml_unknown_runtime_value_is_ignored(tmp_path_project: Path):
    """Defensive: a misconfigured agent yaml (typo, legacy
    'claude-code' value) must not crash the resolver; we leave the
    runtime as-is so the validation error surfaces at spawn time
    via the registry, not from a corrupted resolved config."""
    _write_agent_yaml(
        tmp_path_project,
        "legacy",
        {"id": "legacy", "runtime": "claude-code"},
    )
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(resolved, tmp_path_project, agent_id="legacy")
    # Untouched — claude is the default
    assert resolved.invocation.runtime == "claude"


def test_explicit_session_runtime_beats_agent_yaml(tmp_path_project: Path):
    """If the project (or session) already pinned an explicit runtime
    in spawn_config, the agent yaml does NOT override it. Agent yaml
    is a default; explicit user config wins."""
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"] = {
        "invocation": {"runtime": "claude"},
        "config": {"provider": "claude"},
    }
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    _write_agent_yaml(
        tmp_path_project,
        "reviewer",
        {"id": "reviewer", "runtime": "codex"},
    )

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(resolved, tmp_path_project, agent_id="reviewer")

    # Project explicitly said claude — agent yaml's codex is shadowed.
    assert resolved.invocation.runtime == "claude"
    assert resolved.config.provider == "claude"
