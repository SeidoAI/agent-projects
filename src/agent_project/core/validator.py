"""The validation gate.

`agent-project validate` is the single most important command in the system.
This module implements the engine: load every entity, run every check in the
catalogue, optionally apply auto-fixes, and emit a structured report.

The check catalogue (matches `docs/agent-projects-plan.md` "The Validation
Gate" section):

1. Schema checks — file parses, matches Pydantic model, has required fields
2. UUID — every entity has a uuid4
3. ID format — issues match `<PREFIX>-<N>`, nodes match slug rule
4. Enum values — every enum-typed field has a value present in the active enum
5. Reference integrity — `[[node-id]]`, `blocked_by`, `parent`, `related`,
   `repo`, `agent` all resolve to existing entities
6. Bi-directional consistency — node `related` is symmetric
7. Issue body structure — required Markdown sections, acceptance checkbox,
   stop-and-ask guidance, [[references]] count
8. Status transitions — every issue's status is reachable from start
9. Concept node freshness — content_hash matches live content
10. Artifact presence — completed sessions have all required artifacts
11. ID collision detection — two files claiming the same id
12. Sequence drift — next_issue_number is past max(existing keys)
13. Timestamps — parseable, set
14. Comment provenance — author/type/created_at present, type valid
15. Project standards — standards.md exists if referenced

Auto-fix subset (`--fix`):
- Missing `created_at` / `updated_at` → fill from file mtime
- Drifted `next_issue_number` → bump
- Missing `uuid` → generate uuid4
- Bi-directional `related` mismatch → add the missing side
- Sorted-list normalisation (labels, related)
- Basic ID collision rename (issues a warning about manual reference review)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent_project.core import freshness as freshness_mod
from agent_project.core.enum_loader import EnumRegistry, load_enums
from agent_project.core.id_generator import parse_key
from agent_project.core.parser import ParseError, parse_frontmatter_body
from agent_project.core.reference_parser import extract_references
from agent_project.core.status import is_status_reachable
from agent_project.core.store import (
    ISSUES_DIRNAME,
    PROJECT_CONFIG_FILENAME,
    ProjectNotFoundError,
    load_project,
)
from agent_project.models.comment import Comment
from agent_project.models.issue import Issue
from agent_project.models.node import ConceptNode
from agent_project.models.project import ProjectConfig
from agent_project.models.session import AgentSession

logger = logging.getLogger(__name__)


# ============================================================================
# Result types
# ============================================================================


@dataclass
class CheckResult:
    """One finding from one check.

    Severity is `error` (blocks exit 0), `warning` (exit 1 unless --strict),
    or `fixed` (something the auto-fixer changed).
    """

    code: str
    severity: str  # "error" | "warning" | "fixed"
    message: str
    file: str | None = None
    line: int | None = None
    field: str | None = None
    fix_hint: str | None = None
    # For severity == "fixed"
    before: Any = None
    after: Any = None

    def to_json(self) -> dict[str, Any]:
        """Serialise to the JSON output schema."""
        out: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.file is not None:
            out["file"] = self.file
        if self.line is not None:
            out["line"] = self.line
        if self.field is not None:
            out["field"] = self.field
        if self.fix_hint is not None:
            out["fix_hint"] = self.fix_hint
        if self.severity == "fixed":
            out["before"] = self.before
            out["after"] = self.after
        return out


@dataclass
class ValidationReport:
    """The full output of `validate`."""

    version: int = 1
    exit_code: int = 0
    errors: list[CheckResult] = field(default_factory=list)
    warnings: list[CheckResult] = field(default_factory=list)
    fixed: list[CheckResult] = field(default_factory=list)
    cache_rebuilt: bool = False
    duration_ms: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "exit_code": self.exit_code,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "fixed": len(self.fixed),
                "cache_rebuilt": self.cache_rebuilt,
                "duration_ms": self.duration_ms,
            },
            "errors": [e.to_json() for e in self.errors],
            "warnings": [w.to_json() for w in self.warnings],
            "fixed": [f.to_json() for f in self.fixed],
        }


# ============================================================================
# Validation context
# ============================================================================


@dataclass
class LoadedEntity:
    """A successfully-loaded entity plus the path it came from."""

    rel_path: str
    raw_frontmatter: dict[str, Any]
    body: str
    model: Any  # Issue | ConceptNode | AgentSession | Comment


@dataclass
class ValidationContext:
    """Everything the validator loads up front, before running checks.

    Loading happens once and is shared across every check. Parse and schema
    errors that surface during load are collected here as `CheckResult`s
    so they appear in the final report alongside business-rule failures.
    """

    project_dir: Path
    project_config: ProjectConfig | None = None
    project_load_errors: list[CheckResult] = field(default_factory=list)

    issues: list[LoadedEntity] = field(default_factory=list)
    nodes: list[LoadedEntity] = field(default_factory=list)
    sessions: list[LoadedEntity] = field(default_factory=list)
    comments: list[LoadedEntity] = field(default_factory=list)

    issue_load_errors: list[CheckResult] = field(default_factory=list)
    node_load_errors: list[CheckResult] = field(default_factory=list)
    session_load_errors: list[CheckResult] = field(default_factory=list)
    comment_load_errors: list[CheckResult] = field(default_factory=list)

    enums: EnumRegistry = field(default_factory=EnumRegistry)

    def all_load_errors(self) -> list[CheckResult]:
        return [
            *self.project_load_errors,
            *self.issue_load_errors,
            *self.node_load_errors,
            *self.session_load_errors,
            *self.comment_load_errors,
        ]


# ============================================================================
# Loaders — parse files into the context, capturing errors as CheckResults
# ============================================================================


def _rel_path(project_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_dir))
    except ValueError:
        return str(path)


def _try_load_project(ctx: ValidationContext) -> None:
    try:
        ctx.project_config = load_project(ctx.project_dir)
    except ProjectNotFoundError as exc:
        ctx.project_load_errors.append(
            CheckResult(
                code="schema/project_missing",
                severity="error",
                file=PROJECT_CONFIG_FILENAME,
                message=str(exc),
                fix_hint="Run `agent-project init` to create project.yaml.",
            )
        )
    except (ValueError, yaml.YAMLError) as exc:
        ctx.project_load_errors.append(
            CheckResult(
                code="schema/project_invalid",
                severity="error",
                file=PROJECT_CONFIG_FILENAME,
                message=f"project.yaml failed to parse: {exc}",
                fix_hint="Check the YAML syntax and the field names against ProjectConfig.",
            )
        )


def _load_entity_files(
    ctx: ValidationContext,
    subdir: str,
    model_cls: type,
    bucket: list[LoadedEntity],
    error_bucket: list[CheckResult],
    code_prefix: str,
) -> None:
    """Walk one entity directory and load every YAML file into the context."""
    target = ctx.project_dir / subdir
    if not target.is_dir():
        return
    for path in sorted(target.glob("*.yaml")):
        rel = _rel_path(ctx.project_dir, path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            error_bucket.append(
                CheckResult(
                    code=f"{code_prefix}/io_error",
                    severity="error",
                    file=rel,
                    message=f"Could not read file: {exc}",
                )
            )
            continue
        try:
            frontmatter, body = parse_frontmatter_body(text)
        except ParseError as exc:
            error_bucket.append(
                CheckResult(
                    code=f"{code_prefix}/parse_error",
                    severity="error",
                    file=rel,
                    message=str(exc),
                    fix_hint="Check the frontmatter delimiters (`---`) and YAML syntax.",
                )
            )
            continue
        try:
            model = model_cls.model_validate({**frontmatter, "body": body})
        except ValueError as exc:
            error_bucket.append(
                CheckResult(
                    code=f"{code_prefix}/schema_invalid",
                    severity="error",
                    file=rel,
                    message=f"Schema validation failed: {exc}",
                    fix_hint=(
                        f"Check the field types and required fields for {model_cls.__name__}. "
                        f"Compare against the example file in "
                        f".claude/skills/project-manager/examples/."
                    ),
                )
            )
            continue
        bucket.append(
            LoadedEntity(
                rel_path=rel, raw_frontmatter=frontmatter, body=body, model=model
            )
        )


def _load_comments(ctx: ValidationContext) -> None:
    """Comments live under `docs/issues/<KEY>/comments/<filename>.yaml`."""
    docs_issues = ctx.project_dir / "docs" / ISSUES_DIRNAME
    if not docs_issues.is_dir():
        return
    for issue_dir in sorted(docs_issues.iterdir()):
        comments_dir = issue_dir / "comments"
        if not comments_dir.is_dir():
            continue
        for path in sorted(comments_dir.glob("*.yaml")):
            rel = _rel_path(ctx.project_dir, path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                ctx.comment_load_errors.append(
                    CheckResult(
                        code="comment/io_error",
                        severity="error",
                        file=rel,
                        message=f"Could not read file: {exc}",
                    )
                )
                continue
            try:
                frontmatter, body = parse_frontmatter_body(text)
            except ParseError as exc:
                ctx.comment_load_errors.append(
                    CheckResult(
                        code="comment/parse_error",
                        severity="error",
                        file=rel,
                        message=str(exc),
                    )
                )
                continue
            try:
                model = Comment.model_validate({**frontmatter, "body": body})
            except ValueError as exc:
                ctx.comment_load_errors.append(
                    CheckResult(
                        code="comment/schema_invalid",
                        severity="error",
                        file=rel,
                        message=f"Schema validation failed: {exc}",
                    )
                )
                continue
            ctx.comments.append(
                LoadedEntity(
                    rel_path=rel, raw_frontmatter=frontmatter, body=body, model=model
                )
            )


def load_context(project_dir: Path) -> ValidationContext:
    """Build a ValidationContext by loading every entity in the project.

    Errors during loading are recorded as `CheckResult`s in the appropriate
    bucket so the final report includes them. The validator continues
    running other checks even when some entities fail to load.
    """
    ctx = ValidationContext(project_dir=project_dir)
    _try_load_project(ctx)
    ctx.enums = load_enums(project_dir)
    _load_entity_files(ctx, "issues", Issue, ctx.issues, ctx.issue_load_errors, "issue")
    _load_entity_files(
        ctx, "graph/nodes", ConceptNode, ctx.nodes, ctx.node_load_errors, "node"
    )
    _load_entity_files(
        ctx, "sessions", AgentSession, ctx.sessions, ctx.session_load_errors, "session"
    )
    _load_comments(ctx)
    return ctx


# ============================================================================
# Checks — pure functions over a loaded context
# ============================================================================


REQUIRED_ISSUE_BODY_HEADINGS = (
    "Context",
    "Implements",
    "Repo scope",
    "Requirements",
    "Execution constraints",
    "Acceptance criteria",
    "Test plan",
    "Dependencies",
    "Definition of Done",
)


def check_uuid_present(ctx: ValidationContext) -> list[CheckResult]:
    """Every loaded entity must carry a `uuid` field.

    The model's `default_factory=uuid.uuid4` ensures a UUID is always set on
    Pydantic instances; this check exists to catch the case where someone
    has hand-edited a YAML file and removed the field. We look at the raw
    frontmatter, not the model.
    """
    results: list[CheckResult] = []
    for bucket, kind in (
        (ctx.issues, "issue"),
        (ctx.nodes, "node"),
        (ctx.sessions, "session"),
        (ctx.comments, "comment"),
    ):
        for entity in bucket:
            if "uuid" not in entity.raw_frontmatter:
                results.append(
                    CheckResult(
                        code="uuid/missing",
                        severity="error",
                        file=entity.rel_path,
                        field="uuid",
                        message=f"{kind} has no `uuid` field in frontmatter.",
                        fix_hint="Run with --fix to auto-generate a uuid4.",
                    )
                )
    return results


def check_id_format(ctx: ValidationContext) -> list[CheckResult]:
    """Issue IDs must match `<key_prefix>-<N>` from project.yaml.

    Node and session IDs are validated by the Pydantic model itself.
    """
    if ctx.project_config is None:
        return []
    expected_prefix = ctx.project_config.key_prefix
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        try:
            prefix, _n = parse_key(issue.id)
        except ValueError:
            results.append(
                CheckResult(
                    code="id/format",
                    severity="error",
                    file=entity.rel_path,
                    field="id",
                    message=f"Issue id {issue.id!r} is not in the form <PREFIX>-<N>.",
                )
            )
            continue
        if prefix != expected_prefix:
            results.append(
                CheckResult(
                    code="id/wrong_prefix",
                    severity="error",
                    file=entity.rel_path,
                    field="id",
                    message=(
                        f"Issue id {issue.id!r} has prefix {prefix!r} but the "
                        f"project's key_prefix is {expected_prefix!r}."
                    ),
                    fix_hint=f"Rename the id to {expected_prefix}-N to match project.yaml.",
                )
            )
    return results


def _check_enum_field(
    entity: LoadedEntity,
    enum_name: str,
    field_name: str,
    value: Any,
    enums: EnumRegistry,
    code: str,
) -> CheckResult | None:
    if value is None:
        return None
    if not enums.is_valid(enum_name, str(value)):
        valid = ", ".join(enums.value_ids(enum_name)) or "(none)"
        return CheckResult(
            code=code,
            severity="error",
            file=entity.rel_path,
            field=field_name,
            message=f"{field_name}={value!r} not in active {enum_name} enum.",
            fix_hint=f"Valid values: {valid}",
        )
    return None


def check_enum_values(ctx: ValidationContext) -> list[CheckResult]:
    """Every enum-typed field on every entity must have a value in the active enum."""
    results: list[CheckResult] = []

    for entity in ctx.issues:
        issue: Issue = entity.model
        for enum_name, value in (
            ("issue_status", issue.status),
            ("priority", issue.priority),
            ("executor", issue.executor),
            ("verifier", issue.verifier),
        ):
            r = _check_enum_field(
                entity, enum_name, enum_name, value, ctx.enums, f"enum/{enum_name}"
            )
            if r:
                results.append(r)

    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for enum_name, value in (
            ("node_type", node.type),
            ("node_status", node.status),
        ):
            r = _check_enum_field(
                entity, enum_name, enum_name, value, ctx.enums, f"enum/{enum_name}"
            )
            if r:
                results.append(r)

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        r = _check_enum_field(
            entity,
            "session_status",
            "status",
            session.status,
            ctx.enums,
            "enum/session_status",
        )
        if r:
            results.append(r)
        if session.current_state is not None:
            r2 = _check_enum_field(
                entity,
                "agent_state",
                "current_state",
                session.current_state,
                ctx.enums,
                "enum/agent_state",
            )
            if r2:
                results.append(r2)

    for entity in ctx.comments:
        comment: Comment = entity.model
        r = _check_enum_field(
            entity,
            "comment_type",
            "type",
            comment.type,
            ctx.enums,
            "enum/comment_type",
        )
        if r:
            results.append(r)

    return results


def check_reference_integrity(ctx: ValidationContext) -> list[CheckResult]:
    """All `[[node-id]]`, `blocked_by`, `parent`, `related`, `repo`, `agent` refs resolve."""
    results: list[CheckResult] = []
    issue_ids = {e.model.id for e in ctx.issues}
    node_ids = {e.model.id for e in ctx.nodes}
    repo_slugs = set(ctx.project_config.repos.keys()) if ctx.project_config else set()
    agent_ids = _discover_agent_ids(ctx.project_dir)

    for entity in ctx.issues:
        issue: Issue = entity.model

        # [[node-id]] in body
        for ref in extract_references(issue.body):
            if ref not in node_ids and ref not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/dangling",
                        severity="error",
                        file=entity.rel_path,
                        field="body",
                        message=f"Reference [[{ref}]] does not resolve to any node or issue.",
                        fix_hint=(
                            f"Create graph/nodes/{ref}.yaml or fix the reference. "
                            f"Existing nodes: {sorted(node_ids)[:5]}..."
                            if node_ids
                            else f"Create graph/nodes/{ref}.yaml or fix the reference."
                        ),
                    )
                )

        # blocked_by
        for blocker in issue.blocked_by:
            if blocker not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/blocked_by",
                        severity="error",
                        file=entity.rel_path,
                        field="blocked_by",
                        message=f"blocked_by references unknown issue {blocker!r}.",
                    )
                )

        # parent
        if issue.parent is not None and issue.parent not in issue_ids:
            results.append(
                CheckResult(
                    code="ref/parent",
                    severity="error",
                    file=entity.rel_path,
                    field="parent",
                    message=f"parent references unknown issue {issue.parent!r}.",
                )
            )

        # repo
        if issue.repo and repo_slugs and issue.repo not in repo_slugs:
            results.append(
                CheckResult(
                    code="ref/repo",
                    severity="error",
                    file=entity.rel_path,
                    field="repo",
                    message=(
                        f"repo {issue.repo!r} not declared in project.yaml.repos."
                    ),
                    fix_hint=f"Add {issue.repo!r} to project.yaml under `repos:`.",
                )
            )

    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in node.related:
            if related_id not in node_ids:
                results.append(
                    CheckResult(
                        code="ref/related",
                        severity="error",
                        file=entity.rel_path,
                        field="related",
                        message=f"related references unknown node {related_id!r}.",
                    )
                )
        if (
            node.source
            and node.source.repo
            and repo_slugs
            and node.source.repo not in repo_slugs
        ):
            results.append(
                CheckResult(
                    code="ref/repo",
                    severity="error",
                    file=entity.rel_path,
                    field="source.repo",
                    message=(
                        f"source.repo {node.source.repo!r} not declared in project.yaml.repos."
                    ),
                )
            )
        for ref in extract_references(node.body):
            if ref not in node_ids and ref not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/dangling",
                        severity="error",
                        file=entity.rel_path,
                        field="body",
                        message=f"Reference [[{ref}]] does not resolve.",
                    )
                )

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        for issue_key in session.issues:
            if issue_key not in issue_ids:
                results.append(
                    CheckResult(
                        code="ref/session_issue",
                        severity="error",
                        file=entity.rel_path,
                        field="issues",
                        message=f"session.issues references unknown issue {issue_key!r}.",
                    )
                )
        if agent_ids and session.agent not in agent_ids:
            results.append(
                CheckResult(
                    code="ref/session_agent",
                    severity="error",
                    file=entity.rel_path,
                    field="agent",
                    message=(
                        f"session.agent {session.agent!r} has no matching definition in agents/."
                    ),
                )
            )
        for binding in session.repos:
            if repo_slugs and binding.repo not in repo_slugs:
                results.append(
                    CheckResult(
                        code="ref/repo",
                        severity="error",
                        file=entity.rel_path,
                        field="repos",
                        message=(
                            f"session.repos[].repo {binding.repo!r} not declared in project.yaml.repos."
                        ),
                    )
                )

    for entity in ctx.comments:
        comment: Comment = entity.model
        if comment.issue_key not in issue_ids:
            results.append(
                CheckResult(
                    code="ref/comment_issue",
                    severity="error",
                    file=entity.rel_path,
                    field="issue_key",
                    message=f"Comment.issue_key references unknown issue {comment.issue_key!r}.",
                )
            )

    return results


def _discover_agent_ids(project_dir: Path) -> set[str]:
    """Read `<project>/agents/*.yaml` and return the set of declared agent ids."""
    agents_dir = project_dir / "agents"
    if not agents_dir.is_dir():
        return set()
    ids: set[str] = set()
    for path in sorted(agents_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(raw, dict) and "id" in raw:
            ids.add(str(raw["id"]))
        else:
            ids.add(path.stem)
    return ids


def check_bidirectional_related(ctx: ValidationContext) -> list[CheckResult]:
    """For every node A.related: [B], node B.related must contain A."""
    results: list[CheckResult] = []
    by_id = {e.model.id: e for e in ctx.nodes}
    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in node.related:
            other = by_id.get(related_id)
            if other is None:
                continue  # caught by ref integrity
            if node.id not in other.model.related:
                results.append(
                    CheckResult(
                        code="bidi/related",
                        severity="warning",
                        file=entity.rel_path,
                        field="related",
                        message=(
                            f"Node {node.id!r} declares related {related_id!r}, "
                            f"but {related_id!r} does not declare {node.id!r} in its related list."
                        ),
                        fix_hint="Run with --fix to add the missing back-reference.",
                    )
                )
    return results


def check_issue_body_structure(ctx: ValidationContext) -> list[CheckResult]:
    """Required Markdown headings, acceptance checkbox, stop-and-ask, refs count."""
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        body = issue.body
        for heading in REQUIRED_ISSUE_BODY_HEADINGS:
            if f"## {heading}" not in body:
                results.append(
                    CheckResult(
                        code="body/missing_heading",
                        severity="warning",
                        file=entity.rel_path,
                        field="body",
                        message=f"Issue body is missing required heading `## {heading}`.",
                        fix_hint=f"Add a `## {heading}` section to the issue body.",
                    )
                )

        # Acceptance criteria checkbox
        accept_section = _section(body, "Acceptance criteria")
        if (
            accept_section is not None
            and "- [ ]" not in accept_section
            and "- [x]" not in accept_section
        ):
            results.append(
                CheckResult(
                    code="body/no_acceptance_checkbox",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message="Acceptance criteria section has no checkbox items.",
                )
            )

        # Stop-and-ask guidance
        if "stop and ask" not in body.lower() and "stop, ask" not in body.lower():
            results.append(
                CheckResult(
                    code="body/no_stop_and_ask",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message="Issue body is missing 'stop and ask' guidance for ambiguity.",
                )
            )

        if not extract_references(body):
            results.append(
                CheckResult(
                    code="body/no_references",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message=(
                        "Issue body has no [[references]] to concept nodes — "
                        "potential coherence gap."
                    ),
                    fix_hint=(
                        "Reference the relevant concept nodes (endpoints, models, contracts) "
                        "in the body using [[node-id]]."
                    ),
                )
            )

    return results


def _section(body: str, heading: str) -> str | None:
    marker = f"## {heading}"
    if marker not in body:
        return None
    after = body.split(marker, 1)[1]
    next_heading = after.find("\n## ")
    if next_heading == -1:
        return after
    return after[:next_heading]


def check_status_transitions(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue's status must be reachable from the project's start state."""
    if ctx.project_config is None:
        return []
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if not is_status_reachable(ctx.project_config, issue.status):
            results.append(
                CheckResult(
                    code="status/unreachable",
                    severity="error",
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Issue status {issue.status!r} is not reachable from "
                        f"the start state via project.yaml.status_transitions."
                    ),
                    fix_hint="Check status_transitions in project.yaml.",
                )
            )
    return results


def check_freshness(ctx: ValidationContext) -> list[CheckResult]:
    """Concept node freshness — content_hash must match live content."""
    if ctx.project_config is None:
        return []
    results: list[CheckResult] = []
    nodes = [e.model for e in ctx.nodes]
    rel_by_id = {e.model.id: e.rel_path for e in ctx.nodes}
    for fr in freshness_mod.check_all_nodes(nodes, ctx.project_config):
        rel = rel_by_id.get(fr.node_id, f"graph/nodes/{fr.node_id}.yaml")
        if fr.status == freshness_mod.FreshnessStatus.SOURCE_MISSING:
            results.append(
                CheckResult(
                    code="freshness/source_missing",
                    severity="error",
                    file=rel,
                    field="source",
                    message=fr.detail or f"Source missing for node {fr.node_id}.",
                )
            )
        elif fr.status == freshness_mod.FreshnessStatus.STALE:
            results.append(
                CheckResult(
                    code="freshness/stale",
                    severity="warning",
                    file=rel,
                    field="source.content_hash",
                    message=fr.detail or f"Node {fr.node_id} content_hash is stale.",
                    fix_hint="Run `agent-project node check --update` (deferred to a later release).",
                )
            )
    return results


def check_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Sessions in `completed` status must have all required artifacts."""
    manifest_path = ctx.project_dir / "templates" / "artifacts" / "manifest.yaml"
    if not manifest_path.exists():
        return []
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []
    required_files = [
        a["file"]
        for a in artifacts
        if isinstance(a, dict) and a.get("required") and "file" in a
    ]

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != "completed":
            continue
        artifacts_dir = ctx.project_dir / "sessions" / session.id / "artifacts"
        for artifact_file in required_files:
            if not (artifacts_dir / artifact_file).exists():
                results.append(
                    CheckResult(
                        code="artifact/missing",
                        severity="error",
                        file=entity.rel_path,
                        field="artifacts",
                        message=(
                            f"Completed session {session.id!r} is missing required artifact "
                            f"{artifact_file!r}."
                        ),
                        fix_hint=f"Write sessions/{session.id}/artifacts/{artifact_file}.",
                    )
                )
    return results


def check_id_collisions(ctx: ValidationContext) -> list[CheckResult]:
    """Two entity files claiming the same id with different uuids → error."""
    results: list[CheckResult] = []
    for kind, bucket in (
        ("issue", ctx.issues),
        ("node", ctx.nodes),
        ("session", ctx.sessions),
    ):
        seen: dict[str, list[LoadedEntity]] = {}
        for entity in bucket:
            seen.setdefault(entity.model.id, []).append(entity)
        for entity_id, entities in seen.items():
            if len(entities) <= 1:
                continue
            unique_uuids = {str(e.model.uuid) for e in entities}
            if len(unique_uuids) == 1:
                # Same id and same uuid — duplicate file, weird but not a collision.
                continue
            files = ", ".join(e.rel_path for e in entities)
            results.append(
                CheckResult(
                    code="collision/id",
                    severity="error",
                    file=entities[0].rel_path,
                    field="id",
                    message=(
                        f"{kind} id {entity_id!r} is claimed by multiple files with "
                        f"different uuids: {files}"
                    ),
                    fix_hint="Run with --fix to rename one and rewrite local references.",
                )
            )
    return results


def check_sequence_drift(ctx: ValidationContext) -> list[CheckResult]:
    """`project.yaml.next_issue_number` must be at least max(existing keys) + 1."""
    if ctx.project_config is None:
        return []
    max_n = 0
    for entity in ctx.issues:
        try:
            _, n = parse_key(entity.model.id)
        except ValueError:
            continue
        if n > max_n:
            max_n = n
    expected = max_n + 1
    if ctx.project_config.next_issue_number < expected:
        return [
            CheckResult(
                code="sequence/drift",
                severity="warning",
                file=PROJECT_CONFIG_FILENAME,
                field="next_issue_number",
                message=(
                    f"next_issue_number={ctx.project_config.next_issue_number} but "
                    f"max existing issue key is {max_n}. Counter should be >= {expected}."
                ),
                fix_hint=f"Run with --fix to bump next_issue_number to {expected}.",
            )
        ]
    return []


def check_timestamps(ctx: ValidationContext) -> list[CheckResult]:
    """Every entity should have parseable created_at / updated_at where applicable."""
    results: list[CheckResult] = []
    for kind, bucket in (
        ("issue", ctx.issues),
        ("node", ctx.nodes),
        ("session", ctx.sessions),
    ):
        for entity in bucket:
            for field_name in ("created_at", "updated_at"):
                value = getattr(entity.model, field_name, None)
                if value is None:
                    results.append(
                        CheckResult(
                            code="timestamp/missing",
                            severity="warning",
                            file=entity.rel_path,
                            field=field_name,
                            message=f"{kind} has no {field_name}.",
                            fix_hint=f"Run with --fix to set {field_name} from file mtime.",
                        )
                    )
                elif not isinstance(value, datetime):
                    results.append(
                        CheckResult(
                            code="timestamp/invalid",
                            severity="error",
                            file=entity.rel_path,
                            field=field_name,
                            message=f"{kind} {field_name} is not a valid ISO datetime.",
                        )
                    )
    return results


def check_comment_provenance(ctx: ValidationContext) -> list[CheckResult]:
    """Every comment has author/type/created_at; type is in the active enum."""
    results: list[CheckResult] = []
    for entity in ctx.comments:
        comment: Comment = entity.model
        if not comment.author:
            results.append(
                CheckResult(
                    code="comment/no_author",
                    severity="error",
                    file=entity.rel_path,
                    field="author",
                    message="Comment is missing required field `author`.",
                )
            )
        if not comment.type:
            results.append(
                CheckResult(
                    code="comment/no_type",
                    severity="error",
                    file=entity.rel_path,
                    field="type",
                    message="Comment is missing required field `type`.",
                )
            )
        if comment.created_at is None:
            results.append(
                CheckResult(
                    code="comment/no_created_at",
                    severity="error",
                    file=entity.rel_path,
                    field="created_at",
                    message="Comment is missing required field `created_at`.",
                )
            )
    return results


def check_project_standards(ctx: ValidationContext) -> list[CheckResult]:
    """V0 standards check: just confirm `<project>/standards.md` exists if any
    file references it. Future versions will read project-defined rules.
    """
    standards_path = ctx.project_dir / "standards.md"
    referenced = False
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions):
        for entity in bucket:
            if "standards.md" in entity.body:
                referenced = True
                break
        if referenced:
            break
    if referenced and not standards_path.exists():
        return [
            CheckResult(
                code="standards/missing",
                severity="warning",
                file=None,
                message=(
                    "An entity references standards.md, but standards.md is missing "
                    "from the project root."
                ),
            )
        ]
    return []


# ============================================================================
# Auto-fix
# ============================================================================


def _fix_uuid(entity: LoadedEntity) -> CheckResult | None:
    if "uuid" in entity.raw_frontmatter:
        return None
    new_uuid = str(uuid.uuid4())
    entity.raw_frontmatter = {"uuid": new_uuid, **entity.raw_frontmatter}
    return CheckResult(
        code="uuid/missing",
        severity="fixed",
        file=entity.rel_path,
        field="uuid",
        message="Generated missing uuid.",
        before=None,
        after=new_uuid,
    )


def _fix_timestamps(entity: LoadedEntity, project_dir: Path) -> list[CheckResult]:
    fixes: list[CheckResult] = []
    abs_path = project_dir / entity.rel_path
    try:
        mtime = abs_path.stat().st_mtime
    except OSError:
        return fixes
    iso = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    for field_name in ("created_at", "updated_at"):
        if entity.raw_frontmatter.get(field_name) is None:
            entity.raw_frontmatter[field_name] = iso
            fixes.append(
                CheckResult(
                    code="timestamp/missing",
                    severity="fixed",
                    file=entity.rel_path,
                    field=field_name,
                    message=f"Filled {field_name} from file mtime.",
                    before=None,
                    after=iso,
                )
            )
    return fixes


def _fix_sorted_lists(entity: LoadedEntity) -> list[CheckResult]:
    fixes: list[CheckResult] = []
    for list_field in ("labels", "related", "tags"):
        value = entity.raw_frontmatter.get(list_field)
        if isinstance(value, list) and value != sorted(value):
            entity.raw_frontmatter[list_field] = sorted(value)
            fixes.append(
                CheckResult(
                    code="sorted/list",
                    severity="fixed",
                    file=entity.rel_path,
                    field=list_field,
                    message=f"Sorted {list_field} alphabetically.",
                    before=value,
                    after=sorted(value),
                )
            )
    return fixes


def _fix_bidirectional_related(ctx: ValidationContext) -> list[CheckResult]:
    fixes: list[CheckResult] = []
    by_id = {e.model.id: e for e in ctx.nodes}
    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in list(node.related):
            other = by_id.get(related_id)
            if other is None:
                continue
            if node.id not in other.model.related:
                # Mutate the other entity's raw frontmatter list so the
                # rewrite picks it up. Also update the in-memory model so
                # subsequent checks don't refire on the same mismatch.
                other_related = list(other.raw_frontmatter.get("related", []))
                if node.id not in other_related:
                    other_related.append(node.id)
                    other_related.sort()
                    other.raw_frontmatter["related"] = other_related
                    other.model.related = other_related
                fixes.append(
                    CheckResult(
                        code="bidi/related",
                        severity="fixed",
                        file=other.rel_path,
                        field="related",
                        message=(
                            f"Added back-reference {node.id!r} to {other.model.id!r}.related."
                        ),
                        before=None,
                        after=node.id,
                    )
                )
    return fixes


def _fix_sequence_drift(ctx: ValidationContext) -> CheckResult | None:
    if ctx.project_config is None:
        return None
    max_n = 0
    for entity in ctx.issues:
        try:
            _, n = parse_key(entity.model.id)
        except ValueError:
            continue
        if n > max_n:
            max_n = n
    expected = max_n + 1
    current = ctx.project_config.next_issue_number
    if current >= expected:
        return None
    ctx.project_config.next_issue_number = expected
    project_yaml = ctx.project_dir / PROJECT_CONFIG_FILENAME
    raw = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    if isinstance(raw, dict):
        raw["next_issue_number"] = expected
        project_yaml.write_text(
            yaml.safe_dump(raw, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    return CheckResult(
        code="sequence/drift",
        severity="fixed",
        file=PROJECT_CONFIG_FILENAME,
        field="next_issue_number",
        message=f"Bumped next_issue_number from {current} to {expected}.",
        before=current,
        after=expected,
    )


def _rewrite_entity_file(project_dir: Path, entity: LoadedEntity) -> None:
    """Write a fixed entity back to disk, preserving uuid-first key order."""
    from agent_project.core.parser import serialize_frontmatter_body

    abs_path = project_dir / entity.rel_path
    text = serialize_frontmatter_body(entity.raw_frontmatter, entity.body)
    abs_path.write_text(text, encoding="utf-8")


def apply_fixes(ctx: ValidationContext) -> list[CheckResult]:
    """Apply the auto-fix subset and return a list of fix CheckResults."""
    fixes: list[CheckResult] = []
    dirty: set[str] = set()  # rel_paths that need rewriting

    for bucket in (ctx.issues, ctx.nodes, ctx.sessions, ctx.comments):
        for entity in bucket:
            for fix in _filter_none([_fix_uuid(entity)]):
                fixes.append(fix)
                dirty.add(entity.rel_path)
            for fix in _fix_timestamps(entity, ctx.project_dir):
                fixes.append(fix)
                dirty.add(entity.rel_path)
            for fix in _fix_sorted_lists(entity):
                fixes.append(fix)
                dirty.add(entity.rel_path)

    bidi_fixes = _fix_bidirectional_related(ctx)
    fixes.extend(bidi_fixes)
    for fix in bidi_fixes:
        if fix.file is not None:
            dirty.add(fix.file)

    seq_fix = _fix_sequence_drift(ctx)
    if seq_fix is not None:
        fixes.append(seq_fix)

    # Rewrite every dirty entity file.
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions, ctx.comments):
        for entity in bucket:
            if entity.rel_path in dirty:
                _rewrite_entity_file(ctx.project_dir, entity)

    return fixes


def _filter_none(items: list[Any]) -> list[Any]:
    return [i for i in items if i is not None]


# ============================================================================
# The main entry point
# ============================================================================


ALL_CHECKS = [
    check_uuid_present,
    check_id_format,
    check_enum_values,
    check_reference_integrity,
    check_bidirectional_related,
    check_issue_body_structure,
    check_status_transitions,
    check_freshness,
    check_artifact_presence,
    check_id_collisions,
    check_sequence_drift,
    check_timestamps,
    check_comment_provenance,
    check_project_standards,
]


def validate_project(
    project_dir: Path,
    *,
    strict: bool = False,
    fix: bool = False,
) -> ValidationReport:
    """Run the full validation gate against a project.

    The agent's normal mode is `strict=True, fix=False`. The orchestrator may
    call with `fix=True` to apply auto-fixes after the agent has done its
    initial pass.

    Always rebuilds the graph cache (`graph/index.yaml`) as a side effect —
    incrementally if the cache is already up to date, as a full rebuild if
    the cache is missing or corrupt.
    """
    # Import lazily to avoid a circular import at module load time.
    from agent_project.core import graph_cache

    started = time.monotonic()
    logger.info(
        "validate_project: starting (project=%s, strict=%s, fix=%s)",
        project_dir,
        strict,
        fix,
    )

    ctx = load_context(project_dir)
    logger.debug(
        "validate_project: loaded context (issues=%d, nodes=%d, sessions=%d, comments=%d, load_errors=%d)",
        len(ctx.issues),
        len(ctx.nodes),
        len(ctx.sessions),
        len(ctx.comments),
        len(list(ctx.all_load_errors())),
    )

    findings: list[CheckResult] = list(ctx.all_load_errors())

    fix_results: list[CheckResult] = []
    if fix:
        # Apply fixes BEFORE running checks so the checks don't report
        # things the fixer has already addressed.
        logger.info("validate_project: applying auto-fixes")
        fix_results = apply_fixes(ctx)
        logger.debug("validate_project: applied %d fix(es)", len(fix_results))
        # Re-load context after fixes — the fixes mutated files on disk.
        ctx = load_context(project_dir)
        findings = list(ctx.all_load_errors())

    for check in ALL_CHECKS:
        check_started = time.monotonic()
        results = check(ctx)
        findings.extend(results)
        logger.debug(
            "validate_project: %s -> %d finding(s) in %.1fms",
            check.__name__,
            len(results),
            (time.monotonic() - check_started) * 1000,
        )

    # Rebuild the graph cache as a side effect. Only attempt if the project
    # config loaded successfully — without it, the cache can't be oriented.
    cache_rebuilt = False
    if ctx.project_config is not None:
        try:
            cache_rebuilt = graph_cache.ensure_fresh(project_dir)
        except (OSError, TimeoutError) as exc:
            findings.append(
                CheckResult(
                    code="cache/rebuild_failed",
                    severity="warning",
                    file=graph_cache.INDEX_REL_PATH,
                    message=f"Could not rebuild graph cache: {exc}",
                    fix_hint="Delete graph/index.yaml and re-run validate.",
                )
            )

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    if strict:
        errors.extend(warnings)
        warnings = []

    if errors:
        exit_code = 2
    elif warnings:
        exit_code = 1
    else:
        exit_code = 0

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "validate_project: complete (exit=%d, errors=%d, warnings=%d, fixed=%d, cache_rebuilt=%s, duration=%dms)",
        exit_code,
        len(errors),
        len(warnings),
        len(fix_results),
        cache_rebuilt,
        duration_ms,
    )

    return ValidationReport(
        exit_code=exit_code,
        errors=errors,
        warnings=warnings,
        fixed=fix_results,
        cache_rebuilt=cache_rebuilt,
        duration_ms=duration_ms,
    )


# Re-export for tests / introspection
__all__ = [
    "ALL_CHECKS",
    "CheckResult",
    "LoadedEntity",
    "ValidationContext",
    "ValidationReport",
    "apply_fixes",
    "asdict",  # convenience
    "load_context",
    "validate_project",
]
