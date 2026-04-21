"""Spawn configuration models.

Shared between the tripwire-shipped `templates/spawn/defaults.yaml` and
the per-session `SpawnConfig` override on `AgentSession`. Resolution
with precedence (session > project > tripwire default) happens in
`tripwire.core.spawn_config.load_resolved_spawn_config`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SpawnInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = "claude"
    background: bool = True
    log_path_template: str = (
        "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"
    )


class SpawnConfigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "opus"
    fallback_model: str = "sonnet"
    effort: str = "max"
    permission_mode: str = "bypassPermissions"
    disallowed_tools: list[str] = Field(default_factory=lambda: ["Agent"])
    max_turns: int = 200
    max_budget_usd: int = 50
    output_format: str = "stream-json"


class SpawnDefaults(BaseModel):
    """Full resolved spawn configuration (shipped default + overrides)."""

    model_config = ConfigDict(extra="forbid")

    invocation: SpawnInvocation = Field(default_factory=SpawnInvocation)
    config: SpawnConfigValues = Field(default_factory=SpawnConfigValues)
    prompt_template: str = ""
    system_prompt_append: str = ""
