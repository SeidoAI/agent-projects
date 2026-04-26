"""Verify the v0.7.10 §D2 ``codex-reviewer.yaml`` agent template.

The agent is the codex-side counterpart to backend-coder / verifier:
single-shot, runtime: codex, no implementation work — reads the PR
diff and posts a structured review.

The agent yaml drives the runtime via the KUI-94 §C4 agent-yaml
override mechanism (``_apply_agent_yaml_overrides`` in
``src/tripwire/core/spawn_config.py``); the test below loads the
template, materialises it into a fresh project, and asserts the
override path resolves to ``CodexRuntime``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from tripwire.core.spawn_config import (
    _apply_agent_yaml_overrides,
    load_resolved_spawn_config,
)
from tripwire.runtimes import get_runtime
from tripwire.runtimes.codex import CodexRuntime
from tripwire.templates import get_templates_dir

AGENT_TEMPLATE_REL = Path("agent_templates") / "codex-reviewer.yaml"


def _load_template() -> dict:
    path = get_templates_dir() / AGENT_TEMPLATE_REL
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_template_exists():
    """The packaged template must ship — ``tripwire init`` copies it
    verbatim into ``<project>/agents/codex-reviewer.yaml``."""
    path = get_templates_dir() / AGENT_TEMPLATE_REL
    assert path.is_file(), f"missing template: {path}"


def test_id_and_name_match_filename():
    data = _load_template()
    assert data["id"] == "codex-reviewer"
    assert data["name"]


def test_runtime_is_codex():
    """The whole point of the agent: ``runtime: codex`` flips the
    spawn config to the CodexRuntime instead of ClaudeRuntime."""
    data = _load_template()
    assert data["runtime"] == "codex"


def test_effort_is_high():
    """Per spec §3.D2: ``effort: high`` — review is read-heavy not
    generate-heavy, max effort isn't worth the cost."""
    data = _load_template()
    assert data["effort"] == "high"


def test_model_is_codex_variant():
    """Codex CLI accepts model names like ``gpt-5-codex`` /
    ``gpt-5``. The model field must be set; we don't pin to one
    exact value here so the team can re-tune the variant without
    touching this test."""
    data = _load_template()
    model = data.get("model")
    assert isinstance(model, str) and model
    # Sanity guard: 'opus' / 'sonnet' / 'haiku' are claude-only — a
    # claude model in a runtime: codex agent yaml is almost certainly
    # a copy-paste mistake.
    claude_only = {"opus", "sonnet", "haiku"}
    assert model not in claude_only, (
        f"model={model!r} is a Claude name on a runtime: codex agent — "
        f"see runtimes/codex.py for the codex CLI's expected model names."
    )


def test_permissions_network_includes_github():
    """Per spec §3.D2: ``permissions: { network: [github.com] }`` —
    the agent uses ``gh pr diff`` and ``gh pr comment`` so it needs
    egress to github.com (and api.github.com)."""
    data = _load_template()
    network = data["permissions"]["network"]
    assert any("github.com" in host for host in network)


def test_tools_include_git_and_gh():
    """Per spec §3.D2: ``tools: [git, gh]``. The review flow shells
    out to gh for diff + comment posting."""
    data = _load_template()
    tools = data["tools"]
    assert "git" in tools
    assert "gh" in tools


def test_context_skills_empty():
    """KUI-94 inlines skill content into the codex prompt at spawn
    time (codex has no SKILL.md / .codex/skills/ analogue). The
    agent yaml's context.skills list must therefore be empty for
    codex agents — non-empty here is a config bug that would lead
    to skills being silently dropped."""
    data = _load_template()
    skills = data["context"]["skills"]
    assert skills == [], f"expected empty skills list, got {skills!r}"


def test_context_docs_references_protocol():
    """Per spec §3.D2: ``context.docs: [docs/codex-review-protocol.md]``.
    The doc is the agent's review-protocol prompt — without it the
    agent has no instructions on how to structure the review."""
    data = _load_template()
    docs = data["context"]["docs"]
    assert "docs/codex-review-protocol.md" in docs


def test_yaml_runtime_field_resolves_to_codex_runtime(tmp_path_project: Path):
    """The packaged template, copied into a project's ``agents/``
    directory, must drive the spawn config through
    ``_apply_agent_yaml_overrides`` to produce CodexRuntime. This
    is the integration point KUI-94 §C4 introduced; KUI-95's agent
    yaml is its first user-visible consumer."""
    src = get_templates_dir() / AGENT_TEMPLATE_REL
    agents_dir = tmp_path_project / "agents"
    agents_dir.mkdir(exist_ok=True)
    dest = agents_dir / "codex-reviewer.yaml"
    shutil.copy2(src, dest)

    resolved = load_resolved_spawn_config(tmp_path_project, session=None)
    _apply_agent_yaml_overrides(resolved, tmp_path_project, agent_id="codex-reviewer")

    assert resolved.invocation.runtime == "codex"
    assert resolved.config.provider == "codex"
    assert isinstance(get_runtime(resolved.invocation.runtime), CodexRuntime)
