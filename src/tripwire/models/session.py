"""AgentSession model.

A session is the persistence anchor for one container instance (or many
re-engagements of the same container). It carries:
- the issues the session is working on
- the repos it can branch and PR in (multi-repo, all equal)
- the runtime state (Claude session id, Docker volume, etc.)
- the engagement history (every container start, with trigger and outcome)
- per-session orchestration overrides
- per-session artifact overrides
"""

import uuid as _uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RepoBinding(BaseModel):
    """One repo a session can work in.

    All repos in a session are equal — there is no primary. The agent treats
    them symmetrically, can branch in any, and opens PRs against any.
    """

    model_config = ConfigDict(extra="forbid")

    repo: str  # GitHub slug, e.g. "SeidoAI/web-app-backend"
    base_branch: str
    branch: str | None = None
    pr_number: int | None = None

    # Optional sub-tree prefix. When set, plan-file paths in
    # `**Files:**` blocks resolve relative to `<clone>/<path_prefix>` as
    # well as `<clone>`. Lets frontend plans say `src/app/router.tsx`
    # instead of `src/tripwire/ui/frontend/src/app/router.tsx`.
    path_prefix: str | None = None


class WorktreeEntry(BaseModel):
    """One git worktree created for a session spawn."""

    model_config = ConfigDict(extra="forbid")

    repo: str  # GitHub slug, e.g. "SeidoAI/tripwire"
    clone_path: str  # absolute path to the original clone
    worktree_path: str  # absolute path to the worktree directory
    branch: str  # branch checked out in the worktree

    # v0.7.5 — URL of the draft PR opened at session-start. ``None`` when
    # the worktree had no remote (graceful skip; the legacy create-PR-at-
    # complete path runs instead) or the entry was persisted before
    # v0.7.5 landed.
    draft_pr_url: str | None = None


class RuntimeState(BaseModel):
    """Session-wide runtime handles, persisted across container restarts.

    Per-repo branch and PR live in the RepoBinding entries above. This is
    only for handles that don't have a per-repo dimension.
    """

    model_config = ConfigDict(extra="forbid")

    claude_session_id: str | None = None
    langgraph_thread_id: str | None = None
    workspace_volume: str | None = None
    worktrees: list[WorktreeEntry] = Field(default_factory=list)
    pid: int | None = None
    started_at: datetime | str | None = None
    log_path: str | None = None
    skills_hash: str | None = None  # sentinel for copy_skills idempotency
    last_spawn_resumed: bool = False  # whether last spawn was --resume
    # v0.7.10 §3.A4 — set by the runtime monitor's ActionExecutor when
    # the cost-overrun tripwire fires. The CLI surfaces this as
    # `(over budget)` next to the paused status so a human knows the
    # session was halted by budget, not by a manual pause.
    cost_overrun_at: datetime | str | None = None


class SessionOrchestration(BaseModel):
    """Orchestration override for one session.

    The hierarchy is Project → Session (just two tiers). The session can pick
    a different named pattern via `pattern: <name>` and/or override individual
    fields via `overrides: {key: value}`. Session-level fields win over
    project-level fields — straight field-level override, no deeper merging.
    """

    model_config = ConfigDict(extra="forbid")

    pattern: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class ArtifactSpec(BaseModel):
    """One artifact spec, used both in the project-level manifest and in
    per-session `artifact_overrides`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str | None = None
    produced_at: str  # validated against artifact_phase enum at manifest load
    required: bool = True
    approval_gate: bool = False


class EngagementEntry(BaseModel):
    """One container start, appended to `session.engagements` on every launch."""

    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    trigger: str
    context: str | None = None
    ended_at: datetime | None = None
    outcome: str | None = None


class SpawnConfig(BaseModel):
    """Per-session spawn override — any subset of SpawnDefaults.

    Merged on top of the resolved project + tripwire-default spawn config
    at launch time. See `tripwire.core.spawn_config.load_resolved_spawn_config`.
    """

    model_config = ConfigDict(extra="forbid")

    invocation: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str | None = None
    system_prompt_append: str | None = None


class AgentSession(BaseModel):
    """An agent session — one logical agent invocation that may span many
    container restarts (re-engagements).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    uuid: UUID = Field(default_factory=_uuid.uuid4)

    # Human-readable slug, e.g. "api-endpoints-core".
    id: str

    name: str
    agent: str  # references agents/<id>.yaml in the project repo
    issues: list[str] = Field(default_factory=list)

    # Multi-repo: all repos equal, all writable. Replaces the old single
    # `repo: str` field.
    repos: list[RepoBinding] = Field(default_factory=list)

    # Optional session-level extra docs, merged with agent + issue docs at
    # container launch and mounted read-only at /workspace/docs/<path>.
    docs: list[str] | None = None

    estimated_size: str | None = None
    blocked_by_sessions: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    grouping_rationale: str | None = None

    status: str = "planned"

    # Latest agent state from the most recent `status` message. The
    # orchestration runtime writes this back here as new status messages
    # arrive.
    current_state: str | None = None

    # Per-session orchestration override. None means use the project default.
    orchestration: SessionOrchestration | None = None

    # Per-session artifact overrides on top of templates/artifacts/manifest.yaml.
    artifact_overrides: list[ArtifactSpec] = Field(default_factory=list)

    # v0.7b: per-session spawn config override. Merged with project and
    # tripwire defaults at launch time; session wins.
    spawn_config: SpawnConfig | None = None

    runtime_state: RuntimeState = Field(default_factory=RuntimeState)

    engagements: list[EngagementEntry] = Field(default_factory=list)

    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    body: str = ""
