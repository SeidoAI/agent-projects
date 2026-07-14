"""Spawn configuration models.

Shared between the tripwire-shipped `templates/spawn/defaults.yaml` and
the per-session `SpawnConfig` override on `AgentSession`. Resolution
with precedence (session > project > agent template > tripwire default)
happens in `tripwire.core.spawn_config.load_resolved_spawn_config`.

v0.14.0 — the models declare *structure only*. No field defaults; a
missing required field on the resolved YAML raises ``ValidationError``
at ``model_validate()`` time rather than silently filling from a
Python-side default. The shipped framework floor lives in
``templates/spawn/defaults.yaml``; per-agent floors live in
``templates/agent_templates/<agent>.yaml`` under a ``spawn_config:``
block (v0.14.0); per-project override via project.yaml.spawn_defaults
or ``.tripwire/spawn/defaults.yaml``; per-session override via
``session.spawn_config``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SpawnInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    runtime: Literal["claude", "codex", "manual"]
    # Sandbox policy passed to `codex exec --sandbox …`. Ignored by the
    # claude runtime. read-only is the safe floor for review-class
    # codex sessions; danger-full-access is required for codex sessions
    # that need to write files (planning sessions, eventual code work).
    codex_sandbox: Literal["read-only", "workspace-write", "danger-full-access"]
    background: bool
    log_path_template: str
    # v0.7.9 §A7 — fork an in-flight monitor process alongside the
    # agent. Set false to opt out (e.g. on perf-sensitive hosts or in
    # tests that don't exercise the monitor). The monitor is the
    # enforcement layer for cost / quota / push-loop tripwires.
    monitor: bool
    monitor_log_path_template: str


class SpawnConfigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The model provider. claude=Anthropic CLI, codex=OpenAI Codex CLI.
    # Drives provider-aware validation in spawn_config (warn-and-drop on
    # claude-only flags for codex sessions); the actual runtime dispatch
    # is by `invocation.runtime` (a parallel single-axis field).
    provider: Literal["claude", "codex"]
    model: str
    fallback_model: str
    effort: str
    permission_mode: str
    disallowed_tools: list[str]
    max_turns: int
    max_budget_usd: int
    output_format: str
    # v0.7.10 §3.A2 — pick a route from `templates/spawn/routing.yaml`.
    # Empty string falls back to the routing table's `default:` route
    # (`agentic_loop` ⇒ opus xhigh, matching the existing baseline).
    task_kind: str


class SpawnDefaults(BaseModel):
    """Full resolved spawn configuration (shipped default + overrides)."""

    model_config = ConfigDict(extra="forbid")

    invocation: SpawnInvocation
    config: SpawnConfigValues
    prompt_template: str
    resume_prompt_template: str
    system_prompt_append: str
