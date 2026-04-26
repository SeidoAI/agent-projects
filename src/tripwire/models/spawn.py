"""Spawn configuration models.

Shared between the tripwire-shipped `templates/spawn/defaults.yaml` and
the per-session `SpawnConfig` override on `AgentSession`. Resolution
with precedence (session > project > tripwire default) happens in
`tripwire.core.spawn_config.load_resolved_spawn_config`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SpawnInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = "claude"
    runtime: Literal["claude", "codex", "manual"] = "claude"
    # Sandbox policy passed to `codex exec --sandbox …`. Ignored by the
    # claude runtime. read-only is the safe default for review-class
    # codex sessions; danger-full-access is required for codex sessions
    # that need to write files (planning sessions, eventual code work).
    codex_sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = (
        "read-only"
    )
    background: bool = True
    log_path_template: str = (
        "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"
    )
    # v0.7.9 §A7 — fork an in-flight monitor process alongside the
    # agent. Set false to opt out (e.g. on perf-sensitive hosts or in
    # tests that don't exercise the monitor). Default on; the monitor
    # is the enforcement layer for cost / quota / push-loop tripwires.
    monitor: bool = True
    monitor_log_path_template: str = (
        "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.monitor.log"
    )


class SpawnConfigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The model provider. claude=Anthropic CLI, codex=OpenAI Codex CLI.
    # Drives provider-aware validation in spawn_config (warn-and-drop on
    # claude-only flags for codex sessions); the actual runtime dispatch
    # is by `invocation.runtime` (a parallel single-axis field).
    provider: Literal["claude", "codex"] = "claude"
    model: str = "opus"
    fallback_model: str = "sonnet"
    effort: str = "xhigh"
    permission_mode: str = "bypassPermissions"
    disallowed_tools: list[str] = Field(
        default_factory=lambda: [
            "Agent",
            "AskUserQuestion",
            "SendUserMessage",
        ]
    )
    max_turns: int = 200
    max_budget_usd: int = 100
    output_format: str = "stream-json"
    # v0.7.10 §3.A2 — pick a route from `templates/spawn/routing.yaml`.
    # Empty string falls back to the routing table's `default:` route
    # (`agentic_loop` ⇒ opus xhigh, matching the existing baseline).
    task_kind: str = ""


class SpawnDefaults(BaseModel):
    """Full resolved spawn configuration (shipped default + overrides)."""

    model_config = ConfigDict(extra="forbid")

    invocation: SpawnInvocation = Field(default_factory=SpawnInvocation)
    config: SpawnConfigValues = Field(default_factory=SpawnConfigValues)
    prompt_template: str = ""
    resume_prompt_template: str = ""
    system_prompt_append: str = ""
