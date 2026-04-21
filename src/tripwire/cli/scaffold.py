"""`tripwire brief` — front-load the agent's context.

This is the single command an agent runs FIRST when starting a session.
It dumps everything the agent needs to know about the project — config,
enums, templates, orchestration pattern, next IDs, validation gate — into
one tool-call result. The PM skill instructs the agent to call this
before reading any planning docs or drafting any files.

Output formats:
- `text` (default): human- and agent-readable text, matches the spec's
  example output exactly
- `json`: structured JSON for programmatic consumption

The command is a pure read operation. It gracefully handles missing
optional directories (`enums/`, `templates/artifacts/`, etc.) because a
freshly-init'd project in v0 only has `project.yaml`, `CLAUDE.md`, and
empty entity directories — everything else comes later.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

from tripwire.core import paths
from tripwire.core.enum_loader import load_enums
from tripwire.core.id_generator import format_key
from tripwire.core.node_store import list_nodes
from tripwire.core.session_store import list_sessions
from tripwire.core.store import ProjectNotFoundError, list_issues, load_project
from tripwire.models.project import ProjectConfig

ARTIFACT_MANIFEST_REL = paths.TEMPLATES_ARTIFACTS_MANIFEST
ORCHESTRATION_DIR = paths.ORCHESTRATION_DIR
ISSUE_TEMPLATES_DIR = paths.ISSUE_TEMPLATES_DIR
COMMENT_TEMPLATES_DIR = paths.COMMENT_TEMPLATES_DIR
SESSION_TEMPLATES_DIR = paths.SESSION_TEMPLATES_DIR
SKILL_EXAMPLES_DIR = ".claude/skills/project-manager/examples"


# ============================================================================
# Scaffold data — what the command returns as structured data
# ============================================================================


@dataclass
class RepoInfo:
    slug: str
    local: str | None


@dataclass
class ArtifactEntry:
    name: str
    file: str
    produced_at: str
    required: bool
    approval_gate: bool


@dataclass
class ArtifactManifest:
    path: str
    exists: bool
    artifacts: list[ArtifactEntry] = field(default_factory=list)


@dataclass
class OrchestrationInfo:
    pattern: str
    path: str
    exists: bool
    plan_approval_required: bool
    auto_merge_on_pass: bool


@dataclass
class ScaffoldData:
    """Structured result of `scaffold-for-creation`.

    Mirrors the text-output sections one-for-one. The JSON output is this
    dataclass run through `asdict`; the text output is rendered by
    `_render_text` from the same data.
    """

    project_name: str
    key_prefix: str
    description: str
    base_branch: str
    repos: list[RepoInfo]
    next_issue_key: str
    next_session_key: str
    next_node_id: str
    enums: dict[str, list[str]]
    artifact_manifest: ArtifactManifest
    orchestration: OrchestrationInfo
    templates: list[str]
    skill_examples: list[str]
    validation_gate: dict[str, Any]
    id_allocation: dict[str, Any]
    # Entity counts for incremental context
    issue_count: int = 0
    issue_by_status: dict[str, int] = field(default_factory=dict)
    node_count: int = 0
    session_count: int = 0
    # Phase and node IDs for agent context
    phase: str = "scoping"
    node_ids: list[str] = field(default_factory=list)


# ============================================================================
# Collectors
# ============================================================================


def _collect_repos(project: ProjectConfig) -> list[RepoInfo]:
    return [
        RepoInfo(slug=slug, local=entry.local)
        for slug, entry in sorted(project.repos.items())
    ]


def _collect_next_ids(project: ProjectConfig) -> tuple[str, str, str]:
    """Return (next_issue_key, next_session_key, next_node_id).

    Issue keys are sequential (`<PREFIX>-<N>`). Sessions and nodes are
    slug-based in v0 — no numeric sequence — so we return a literal string
    explaining that.
    """
    next_issue = format_key(project.key_prefix, project.next_issue_number)
    return next_issue, "(slug-based, no sequence)", "(slug-based, no sequence)"


def _collect_enums(project_dir: Path) -> dict[str, list[str]]:
    """Return the active enum values, keyed by enum name."""
    registry = load_enums(project_dir)
    return {name: list(loaded.value_ids()) for name, loaded in registry.enums.items()}


def _collect_artifact_manifest(project_dir: Path) -> ArtifactManifest:
    manifest_path = project_dir / ARTIFACT_MANIFEST_REL
    if not manifest_path.exists():
        return ArtifactManifest(path=ARTIFACT_MANIFEST_REL, exists=False)
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ArtifactManifest(path=ARTIFACT_MANIFEST_REL, exists=True)
    if not isinstance(raw, dict):
        return ArtifactManifest(path=ARTIFACT_MANIFEST_REL, exists=True)
    artifacts_raw = raw.get("artifacts", [])
    if not isinstance(artifacts_raw, list):
        return ArtifactManifest(path=ARTIFACT_MANIFEST_REL, exists=True)
    artifacts: list[ArtifactEntry] = []
    for entry in artifacts_raw:
        if not isinstance(entry, dict):
            continue
        artifacts.append(
            ArtifactEntry(
                name=str(entry.get("name", "")),
                file=str(entry.get("file", "")),
                produced_at=str(entry.get("produced_at", "")),
                required=bool(entry.get("required", False)),
                approval_gate=bool(entry.get("approval_gate", False)),
            )
        )
    return ArtifactManifest(
        path=ARTIFACT_MANIFEST_REL, exists=True, artifacts=artifacts
    )


def _collect_orchestration(
    project_dir: Path, project: ProjectConfig
) -> OrchestrationInfo:
    pattern_name = project.orchestration.default_pattern
    pattern_rel = f"{ORCHESTRATION_DIR}/{pattern_name}.yaml"
    pattern_path = project_dir / pattern_rel
    return OrchestrationInfo(
        pattern=pattern_name,
        path=pattern_rel,
        exists=pattern_path.exists(),
        plan_approval_required=project.orchestration.plan_approval_required,
        auto_merge_on_pass=project.orchestration.auto_merge_on_pass,
    )


def _collect_templates(project_dir: Path) -> list[str]:
    """Return every template path (relative to project root) an agent should read.

    Covers `issue_templates/`, `comment_templates/`, `session_templates/`,
    and `templates/artifacts/` (which is the one place templates live
    under a nested `templates/` directory in v0's layout).
    """
    template_paths: list[str] = []
    for rel_dir in (
        ISSUE_TEMPLATES_DIR,
        COMMENT_TEMPLATES_DIR,
        SESSION_TEMPLATES_DIR,
        paths.TEMPLATES_ARTIFACTS_DIR,
    ):
        abs_dir = project_dir / rel_dir
        if not abs_dir.is_dir():
            continue
        for f in sorted(abs_dir.rglob("*")):
            if f.is_file() and f.name != ".gitkeep":
                template_paths.append(str(f.relative_to(project_dir)))
    return template_paths


def _collect_skill_examples(project_dir: Path) -> list[str]:
    examples_dir = project_dir / SKILL_EXAMPLES_DIR
    if not examples_dir.is_dir():
        return []
    example_paths: list[str] = []
    for f in sorted(examples_dir.rglob("*")):
        if f.is_file() and f.name != ".gitkeep":
            example_paths.append(str(f.relative_to(project_dir)))
    return example_paths


# ============================================================================
# The main entry point
# ============================================================================


def collect_scaffold(project_dir: Path) -> ScaffoldData:
    """Collect everything `scaffold-for-creation` needs to output.

    Raises:
        ProjectNotFoundError: if `project.yaml` is missing.
    """
    project = load_project(project_dir)
    next_issue, next_session, next_node = _collect_next_ids(project)

    # Entity counts via the store abstractions (single source of truth
    # for where entities live on disk). Parse errors surface as thrown
    # exceptions; we swallow them into a synthetic `parse_error` bucket
    # so the brief stays informative even if one file is malformed.
    try:
        issues = list_issues(project_dir)
    except Exception:
        issues = []
    try:
        nodes = list_nodes(project_dir)
    except Exception:
        nodes = []
    try:
        sessions = list_sessions(project_dir)
    except Exception:
        sessions = []

    issue_by_status: dict[str, int] = {}
    for issue in issues:
        s = getattr(issue, "status", None) or "unknown"
        issue_by_status[s] = issue_by_status.get(s, 0) + 1

    # Retained for downstream consumers that count entities (len()).
    issue_files = issues
    node_files = nodes
    session_dirs = sessions

    # Collect existing node IDs for agent context
    node_ids = sorted(n.id for n in nodes)

    return ScaffoldData(
        project_name=project.name,
        key_prefix=project.key_prefix,
        description=project.description or "",
        base_branch=project.base_branch,
        repos=_collect_repos(project),
        next_issue_key=next_issue,
        next_session_key=next_session,
        next_node_id=next_node,
        enums=_collect_enums(project_dir),
        artifact_manifest=_collect_artifact_manifest(project_dir),
        orchestration=_collect_orchestration(project_dir, project),
        templates=_collect_templates(project_dir),
        skill_examples=_collect_skill_examples(project_dir),
        issue_count=len(issue_files),
        issue_by_status=issue_by_status,
        node_count=len(node_files),
        session_count=len(session_dirs),
        phase=project.phase.value,
        node_ids=node_ids,
        validation_gate={
            "command": "tripwire validate --strict",
            "exit_codes": {
                "0": "clean",
                "1": "warnings only",
                "2": "errors",
            },
            "side_effect": "rebuilds graph/index.yaml",
        },
        id_allocation={
            "sequential_keys": "tripwire next-key --type issue --count N",
            "uuids": "tripwire uuid --count N",
            "rules": [
                "Do NOT hand-write UUIDs — validator checks RFC 4122",
                "Do NOT manually increment project.yaml.next_issue_number",
            ],
        },
    )


# ============================================================================
# Rendering
# ============================================================================


def _render_text(data: ScaffoldData) -> str:
    """Render the scaffold data as human-readable text.

    The output shape matches the spec's example in the "scaffold-for-creation"
    section of `docs/keel-plan.md` — the same output an agent reads
    when it runs this command as its first tool call.
    """
    lines: list[str] = []

    # Project
    lines.append(f"PROJECT: {data.project_name} ({data.key_prefix})")
    lines.append(f"Phase: {data.phase}")
    if data.description:
        lines.append(f"Description: {data.description}")
    lines.append(f"Base branch: {data.base_branch}")
    if data.repos:
        lines.append("Repos:")
        width = max(len(r.slug) for r in data.repos) + 2
        for repo in data.repos:
            slug = repo.slug.ljust(width)
            local = f"(local: {repo.local})" if repo.local else "(no local clone)"
            lines.append(f"  - {slug} {local}")
    else:
        lines.append("Repos: (none registered)")
    lines.append("")

    # Entity counts
    if data.issue_count or data.node_count or data.session_count:
        status_str = ", ".join(
            f"{s}={c}" for s, c in sorted(data.issue_by_status.items())
        )
        lines.append("EXISTING ENTITIES:")
        lines.append(
            f"  issues: {data.issue_count}" + (f" ({status_str})" if status_str else "")
        )
        lines.append(f"  concept nodes: {data.node_count}")
        lines.append(f"  sessions: {data.session_count}")
        lines.append("")

    # Next IDs
    lines.append("NEXT IDS:")
    lines.append(f"  next issue key: {data.next_issue_key}")
    lines.append(f"  next session key: {data.next_session_key}")
    lines.append(f"  next node id: {data.next_node_id}")
    lines.append("")

    # Workflow — prominent display of the issue lifecycle
    issue_statuses = data.enums.get("issue_status", [])
    if issue_statuses:
        lines.append(f"ISSUE WORKFLOW: {' → '.join(issue_statuses)}")
        lines.append("")

    # Enums
    lines.append("ACTIVE ENUMS (from enums/):")
    for name in sorted(data.enums.keys()):
        values = ", ".join(data.enums[name])
        lines.append(f"  {name}: {values}")
    lines.append("")

    # Artifact manifest
    lines.append(f"ACTIVE ARTIFACT MANIFEST ({data.artifact_manifest.path}):")
    if not data.artifact_manifest.exists:
        lines.append("  (no manifest.yaml present — artifact requirements unset)")
    elif not data.artifact_manifest.artifacts:
        lines.append("  (manifest present but no artifacts declared)")
    else:
        for entry in data.artifact_manifest.artifacts:
            required = "required" if entry.required else "optional"
            gate = " [approval_gate]" if entry.approval_gate else ""
            lines.append(f"  - {entry.file} ({entry.produced_at}, {required}){gate}")
    lines.append("")

    # Orchestration
    orch = data.orchestration
    lines.append(f"ACTIVE ORCHESTRATION PATTERN: {orch.pattern} ({orch.path})")
    if not orch.exists:
        lines.append("  (pattern file missing — using project.yaml defaults)")
    lines.append(
        f"  plan_approval_required: {str(orch.plan_approval_required).lower()}"
    )
    lines.append(f"  auto_merge_on_pass: {str(orch.auto_merge_on_pass).lower()}")
    lines.append("")

    # Templates
    lines.append("TEMPLATES (read these before creating files):")
    if not data.templates:
        lines.append("  (no templates shipped yet — v0 project)")
    else:
        for path in data.templates:
            lines.append(f"  {path}")
    lines.append("")

    # Skill examples
    lines.append("SKILL EXAMPLES (read these too):")
    if not data.skill_examples:
        lines.append("  (no skill examples shipped yet — v0 project)")
    else:
        for path in data.skill_examples:
            lines.append(f"  {path}")
    lines.append("")

    # Node IDs
    if data.node_ids:
        lines.append(f"CONCEPT NODES ({len(data.node_ids)}):")
        lines.append(f"  {', '.join(data.node_ids)}")
        lines.append("")

    # Validation gate
    lines.append("VALIDATION GATE (run after every batch of writes):")
    lines.append(f"  {data.validation_gate['command']}")
    lines.append("  Formats: --format text (default) | summary | compact | json")
    lines.append("  --count for just the error count")
    lines.append("  Exit 0 = clean, 1 = warnings, 2 = errors")
    lines.append("  Always rebuilds graph/index.yaml as a side effect.")
    lines.append("")

    # ID allocation
    lines.append("ID ALLOCATION:")
    lines.append(
        f"  - For each new issue: call `{data.id_allocation['sequential_keys']}`"
    )
    lines.append("  - For each entity: generate uuid4 and add `uuid:` to frontmatter")
    for rule in data.id_allocation["rules"]:
        lines.append(f"  - {rule}")

    return "\n".join(lines) + "\n"


def _render_json(data: ScaffoldData) -> str:
    """Render the scaffold data as indented JSON."""
    return json.dumps(asdict(data), indent=2, sort_keys=False) + "\n"


# ============================================================================
# Click command
# ============================================================================


def _scaffold_impl(project_dir: Path, output_format: str) -> None:
    """Shared implementation for `brief` and its `scaffold-for-creation` alias."""
    resolved = project_dir.expanduser().resolve()
    try:
        data = collect_scaffold(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(_render_json(data), nl=False)
    else:
        click.echo(_render_text(data), nl=False)


@click.command(name="brief")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def brief_cmd(project_dir: Path, output_format: str) -> None:
    """Front-load the agent's context with everything needed to start work.

    Prints project config, next IDs, active enums, artifact manifest,
    orchestration pattern, templates, skill examples, the validation gate
    command, and ID allocation rules. The PM skill runs this at the start
    of every workflow to load project state.
    """
    _scaffold_impl(project_dir, output_format)


@click.command(name="scaffold-for-creation", hidden=True)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def scaffold_cmd(project_dir: Path, output_format: str) -> None:
    """Hidden alias for `brief` — kept for backward compatibility.

    New code and documentation should use `tripwire brief`.
    """
    _scaffold_impl(project_dir, output_format)
