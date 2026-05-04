"""ProjectConfig model — represents `<project>/project.yaml`.

The project config is the entry point for every CLI command and the
authoritative source for repo registry, status flow, label categories,
graph settings, the orchestration default, and the next-issue counter
used by `tripwire next-key`.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tripwire.models.manifest import ArtifactEntry


class ProjectPhase(str, Enum):
    """Workflow phases for phase-aware validation.

    The validator enforces different requirements depending on the current
    phase.  The PM agent advances the phase by editing ``project.yaml``
    directly; the validator blocks transitions that don't meet the
    phase-specific requirements.
    """

    scoping = "scoping"
    scoped = "scoped"
    executing = "executing"
    reviewing = "reviewing"


class RepoEntry(BaseModel):
    """One repo in `project.yaml.repos`.

    The repo is keyed in the parent dict by GitHub slug; the entry holds the
    optional local clone path used for fast freshness checks.
    """

    model_config = ConfigDict(extra="forbid")

    local: str | None = None


class GraphSettings(BaseModel):
    """`project.yaml.graph` — concept graph settings."""

    model_config = ConfigDict(extra="forbid")

    node_types: list[str] = Field(default_factory=list)
    auto_index: bool = True


class LabelCategories(BaseModel):
    """`project.yaml.label_categories` — categorised labels.

    Each category is a list of allowed values; an empty list means "any
    label in this category is allowed".
    """

    model_config = ConfigDict(extra="forbid")

    executor: list[str] = Field(default_factory=list)
    verifier: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    agent: list[str] = Field(default_factory=list)


class OrchestrationConfig(BaseModel):
    """`project.yaml.orchestration` — orchestration defaults for the project.

    The named pattern is loaded from `<project>/orchestration/<name>.yaml`.
    Sessions can override either the named pattern or individual fields.
    """

    model_config = ConfigDict(extra="allow")

    default_pattern: str = "default"
    plan_approval_required: bool = False
    auto_merge_on_pass: bool = False


class ProjectWorkspacePointer(BaseModel):
    """Workspace this project is linked to (v0.6b).

    Object form reserves room for future extensions (remote URLs, pinning
    a workspace SHA). Currently only ``path`` is supported; URL support
    arrives in a later release.
    """

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    # url: str | None = None  # future

    @model_validator(mode="after")
    def _at_least_one_target(self) -> "ProjectWorkspacePointer":
        if self.path is None:  # and self.url is None
            raise ValueError("workspace pointer requires `path`")
        return self


class ProjectJitPromptExtra(BaseModel):
    """One entry in ``project.yaml.jit_prompts.extra`` — a project-local
    JIT prompt registered alongside the built-ins.

    Either ``cls`` (a dotted Python path resolvable by ``import``) or
    ``module`` (a path to a project-local Python file) must be set.
    The loader resolves the class via :mod:`importlib`.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    fires_on: str
    cls: str | None = Field(default=None, alias="class")
    module: str | None = None


class ProjectJitPromptsConfig(BaseModel):
    """``project.yaml.jit_prompts`` — opt-out + extras for JIT prompts.

    ``enabled`` defaults to True; setting it False disables ALL
    JIT prompts (including the built-in self-review) for the project AND
    suppresses pre-push hook installation at session-spawn time.
    ``opt_out`` is a list of session IDs that bypass JIT prompts; it
    lives at the project level on purpose so the executing agent
    can't see "no JIT prompts here" in their session.yaml.
    ``extra`` lets a project register its own JIT prompts.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    opt_out: list[str] = Field(default_factory=list)
    extra: list[ProjectJitPromptExtra] = Field(default_factory=list)


class ArtifactManifestRequirements(BaseModel):
    """`project.yaml.artifact_manifest` — the v0.7.9 correctness contract.

    Lists the files that MUST exist on the merged-main snapshot of the PT
    repo whenever a session or issue reaches ``status: done``. Validated
    by the ``done_implies_issue_artifacts_on_main`` rule. Defaults match
    spec §A1.
    """

    model_config = ConfigDict(extra="forbid")

    session_required: list[str] = Field(
        default_factory=lambda: [
            "task-checklist.md",
            "verification-checklist.md",
            "self-review.md",
            "pm-response.yaml",
            "insights.yaml",
        ]
    )
    issue_required: list[str] = Field(
        default_factory=lambda: ["developer.md", "verified.md"]
    )


class MonitorSessionCrashConfig(BaseModel):
    """Threshold values for the ``signal.session_crashed`` predicate."""

    model_config = ConfigDict(extra="forbid")

    stale_engagement_minutes: int = 15
    no_heartbeat_minutes: int = 5


class MonitorSessionPausedQuestionConfig(BaseModel):
    """Threshold values for ``signal.session_paused_question``."""

    model_config = ConfigDict(extra="forbid")

    no_human_reply_minutes: int = 10


class MonitorWorkflowDriftConfig(BaseModel):
    """Threshold values for ``signal.workflow_drift_detected``."""

    model_config = ConfigDict(extra="forbid")

    min_severity: str = "warning"


class MonitorConfig(BaseModel):
    """``project.yaml.monitor`` — pm-monitor signal thresholds.

    The overseer loop in ``workflow.yaml::pm-monitor`` reads these to
    decide when each ``signal.*`` predicate fires. See
    ``references/MONITOR_CRITERIA.md``. Tunable per-project so the
    initial code-shipped values can be calibrated by use rather than
    re-released every time a threshold needs an adjustment.
    """

    model_config = ConfigDict(extra="forbid")

    tick_seconds: int = 60
    session_crash: MonitorSessionCrashConfig = Field(
        default_factory=MonitorSessionCrashConfig
    )
    session_paused_question: MonitorSessionPausedQuestionConfig = Field(
        default_factory=MonitorSessionPausedQuestionConfig
    )
    stale_node_count_high: int = 5
    workflow_drift: MonitorWorkflowDriftConfig = Field(
        default_factory=MonitorWorkflowDriftConfig
    )


class ProjectConfig(BaseModel):
    """The project's root config, parsed from `<project>/project.yaml`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Integer schema/contract version. KUI-126 / A1.
    version: int = 1

    # KUI-127 / A2: PM-set marker for the latest contract-change version.
    contract_changed_at: int | None = None

    name: str
    key_prefix: str
    description: str | None = None
    base_branch: str = "test"
    environments: list[str] = Field(default_factory=list)

    repos: dict[str, RepoEntry] = Field(default_factory=dict)

    statuses: list[str] = Field(default_factory=list)
    status_transitions: dict[str, list[str]] = Field(default_factory=dict)

    label_categories: LabelCategories = Field(default_factory=LabelCategories)

    graph: GraphSettings = Field(default_factory=GraphSettings)

    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)

    next_issue_number: int = 1
    next_session_number: int = 1

    # Workflow phase — drives phase-aware validation checks.
    phase: ProjectPhase = ProjectPhase.scoping

    created_at: datetime | None = None

    # v0.6b: optional workspace link. Absence means standalone project.
    workspace: ProjectWorkspacePointer | None = None

    # v0.7.9 (§A1): the correctness contract. Required artifacts that
    # must exist on merged main for any session/issue with status==done.
    # Enforced by validator rule `done_implies_issue_artifacts_on_main`.
    artifact_manifest: ArtifactManifestRequirements = Field(
        default_factory=ArtifactManifestRequirements
    )

    # v0.8.0 (KUI-99): JIT prompt opt-out + project-local extras.
    # Defaults match the spec: enabled, no opt-outs, no extras. Setting
    # ``enabled: false`` disables ALL JIT prompts for this project (and
    # the pre-push hook installation in runtimes/prep.py).
    jit_prompts: ProjectJitPromptsConfig = Field(
        default_factory=ProjectJitPromptsConfig
    )

    # v0.9.6 (workflow codification stage 1): pm-monitor signal
    # thresholds. The overseer loop reads these at tick time to decide
    # which signals fire. Defaults are starting values to iterate on.
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)

    # v0.7b: per-project artifact manifest overrides layered on top of
    # templates/artifacts/manifest.yaml. Useful for adding project-specific
    # artifacts (e.g. "security-review-doc") without forking the manifest.
    artifact_manifest_overrides: list[ArtifactEntry] = Field(default_factory=list)

    # v0.7b: per-issue artifact manifest overrides. Phase 2 tightens the
    # element type to IssueArtifactEntry; using list[dict] here keeps Phase 0
    # unblocked and parses freely.
    issue_artifact_manifest_overrides: list[dict] = Field(default_factory=list)

    # v0.7b: project-level spawn config override. Free-form mapping merged
    # on top of tripwire defaults; deep-merged with session-level overrides
    # by the spawn config resolver.
    spawn_defaults: dict[str, Any] | None = None

    # v0.7b: pinned tripwire CLI version for project CI. Set at `tripwire init`
    # time and used by the generated `.github/workflows/tripwire.yml`.
    tripwire_version: str | None = None

    # v0.9 (KUI-149 / D7): per-project threshold overrides for the lint
    # rules. Shape `{lint_name: {threshold_name: value}}`; missing keys
    # fall back to packaged defaults (see
    # tripwire.core.validator.lint._thresholds.DEFAULT_THRESHOLDS). Free-
    # form because lints come and go between releases — every key is
    # advisory. A `_schema_version` field is intentionally absent until
    # the v1.0 contract publishes (TW1-4).
    lint_config: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # v0.7.6: SSH URL of the project-tracking repo on GitHub (the repo that
    # holds this project.yaml). Recorded by `tripwire init` after auto-creating
    # the repo; absent on pre-v0.7.6 projects. Disambiguates from `repos:`
    # (code repos) and powers the UI's "open in GitHub" affordance.
    project_repo_url: str | None = None

    # Free-form per-project metadata, never used by the package itself.
    metadata: dict[str, Any] = Field(default_factory=dict)
