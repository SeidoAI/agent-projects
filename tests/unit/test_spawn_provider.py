"""Provider-aware spawn config (KUI-94 C3).

Codex sessions warn — but don't error — on Claude-only flags. Verified
fields: ``disallowed_tools`` and ``fallback_model`` are reset (codex
has no equivalent and the values would never be honoured); ``max_turns``
and ``system_prompt_append`` are preserved (the runtime/monitor adapt
them — see decisions.md).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from tripwire.core.spawn_config import load_resolved_spawn_config


def _set_project_provider(project_dir: Path, provider: str) -> None:
    """Pin the project to a given provider via project.yaml."""
    project_yaml = project_dir / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"] = {
        "config": {"provider": provider},
        "invocation": {"runtime": provider},
    }
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_provider_defaults_to_claude(tmp_path_project: Path):
    """No explicit provider in any layer → claude (matches default
    runtime so existing sessions are unaffected)."""
    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    assert resolved.config.provider == "claude"


def test_codex_session_drops_disallowed_tools_with_warning(
    tmp_path_project: Path,
):
    """A codex session inheriting tripwire's default disallowed_tools
    (Agent, AskUserQuestion, SendUserMessage) gets a clean empty list
    + a one-shot UserWarning. The flag has no codex equivalent and
    silently keeping it would mislead readers of the resolved config."""
    _set_project_provider(tmp_path_project, "codex")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = load_resolved_spawn_config(tmp_path_project, session=None)

    assert resolved.config.provider == "codex"
    assert resolved.config.disallowed_tools == []
    msgs = [str(w.message) for w in caught]
    assert any("disallowed_tools" in m for m in msgs)


def test_codex_session_drops_fallback_model_with_warning(
    tmp_path_project: Path,
):
    """fallback_model is claude-specific (auto-fallback to a smaller
    Anthropic model on Opus 5xx). Codex sessions get it cleared to ''
    so it can't be quietly threaded into argv."""
    _set_project_provider(tmp_path_project, "codex")
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"]["config"]["fallback_model"] = "sonnet"
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = load_resolved_spawn_config(tmp_path_project, session=None)

    assert resolved.config.fallback_model == ""
    msgs = [str(w.message) for w in caught]
    assert any("fallback_model" in m for m in msgs)


def test_codex_session_keeps_max_turns_with_informational_warning(
    tmp_path_project: Path,
):
    """max_turns has no flag analogue but the in-flight monitor
    enforces it from the JSONL stream — keep the value, but warn the
    user that enforcement is monitor-side, not flag-side."""
    _set_project_provider(tmp_path_project, "codex")
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"]["config"]["max_turns"] = 50
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = load_resolved_spawn_config(tmp_path_project, session=None)

    # Value preserved so monitor can enforce
    assert resolved.config.max_turns == 50
    msgs = [str(w.message) for w in caught]
    assert any("max_turns" in m and "monitor" in m.lower() for m in msgs)


def test_codex_session_keeps_system_prompt_append_with_informational_warning(
    tmp_path_project: Path,
):
    """Codex has no --append-system-prompt flag; build_codex_args
    prepends the value to the user prompt instead. Keep the value but
    surface a warning so the operator knows the semantic is different."""
    _set_project_provider(tmp_path_project, "codex")
    project_yaml = tmp_path_project / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["spawn_defaults"]["system_prompt_append"] = "RULES BLOCK"
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = load_resolved_spawn_config(tmp_path_project, session=None)

    # Preserved so the runtime can prepend
    assert resolved.system_prompt_append == "RULES BLOCK"
    msgs = [str(w.message) for w in caught]
    assert any("system_prompt_append" in m for m in msgs)


def test_claude_session_emits_no_provider_warnings(tmp_path_project: Path):
    """Sanity: claude sessions are unaffected by the provider-aware
    validation — no warnings even with all flags fully populated."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = load_resolved_spawn_config(tmp_path_project, session=None)

    assert resolved.config.provider == "claude"
    msgs = [str(w.message) for w in caught]
    assert not any(
        any(k in m for k in ("disallowed_tools", "fallback_model", "max_turns"))
        for m in msgs
    )
