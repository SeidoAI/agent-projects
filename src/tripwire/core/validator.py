"""The validation gate.

`tripwire validate` is the single most important command in the system.
This module implements the engine: load every entity, run every check in the
catalogue, optionally apply auto-fixes, and emit a structured report.

The check catalogue (matches `docs/keel-plan.md` "The Validation
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
from pydantic import ValidationError

from tripwire.core import freshness as freshness_mod
from tripwire.core import paths
from tripwire.core.enum_loader import EnumRegistry, load_enums
from tripwire.core.id_generator import parse_key
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.core.reference_parser import extract_references
from tripwire.core.status import is_status_reachable
from tripwire.core.store import (
    PROJECT_CONFIG_FILENAME,
    ProjectNotFoundError,
    load_project,
)
from tripwire.models.comment import Comment
from tripwire.models.issue import Issue
from tripwire.models.manifest import ArtifactManifest
from tripwire.models.node import ConceptNode
from tripwire.models.project import ProjectConfig
from tripwire.models.session import AgentSession

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

    @property
    def findings(self) -> list[CheckResult]:
        """All findings, errors + warnings + fixed, in a single list.

        Convenience for callers (and tests) that want to scan for a
        specific code without having to know which bucket it landed in.
        """
        return [*self.errors, *self.warnings, *self.fixed]

    @property
    def category_summary(self) -> dict[str, dict[str, int]]:
        """Group findings by category (the prefix before ``/``)."""
        cats: dict[str, dict[str, int]] = {}
        for finding in [*self.errors, *self.warnings, *self.fixed]:
            cat = finding.code.split("/")[0] if "/" in finding.code else finding.code
            if cat not in cats:
                cats[cat] = {"errors": 0, "warnings": 0, "fixed": 0}
            if finding.severity == "error":
                cats[cat]["errors"] += 1
            elif finding.severity == "warning":
                cats[cat]["warnings"] += 1
            elif finding.severity == "fixed":
                cats[cat]["fixed"] += 1
        return cats

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
            "categories": self.category_summary,
            "errors": [e.to_json() for e in self.errors],
            "warnings": [w.to_json() for w in self.warnings],
            "fixed": [f.to_json() for f in self.fixed],
        }

    def to_summary(self) -> str:
        """One-line header + error-code counts.  Compact for agent consumption."""
        from collections import Counter

        lines: list[str] = []
        if self.exit_code == 0:
            lines.append("validate passed")
        else:
            lines.append(
                f"validate: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s)"
            )
        codes: Counter[str] = Counter()
        for e in self.errors:
            codes[e.code] += 1
        for w in self.warnings:
            codes[f"{w.code} (warning)"] += 1
        for code, count in codes.most_common():
            lines.append(f"  {code}: {count}")
        return "\n".join(lines)

    def to_compact(self) -> str:
        """One line per finding: ``file  code  message``.

        Useful for scanning and fixing errors one by one.
        """
        lines: list[str] = []
        for finding in [*self.errors, *self.warnings]:
            file_part = finding.file or ""
            lines.append(f"{file_part}\t{finding.code}\t{finding.message}")
        return "\n".join(lines)


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
                fix_hint="Run `tripwire init` to create project.yaml.",
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


# Loader convention
# -----------------
# Each entity type gets a dedicated `_load_<type>` function. Don't try to
# abstract them into a single generic loader — the directory layouts vary
# (nodes are flat, issues and sessions are directories with a fixed child
# filename), and the previous attempt at a generic helper is what let the
# session-directory bug hide in Phase 1-2: the shared glob was `*.yaml`,
# which silently skipped every directory-layout entity. If you add a new
# entity type, copy the closest existing loader (sessions/issues for
# directory layout; nodes for flat layout) and adapt the error codes.


def _load_nodes(ctx: ValidationContext) -> None:
    """Load every concept node at `nodes/<id>.yaml`.

    Nodes are flat YAML files (unlike issues and sessions which have
    per-entity directories).
    """
    nodes_root = paths.nodes_dir(ctx.project_dir)
    if not nodes_root.is_dir():
        return
    for path in sorted(nodes_root.glob("*.yaml")):
        rel = _rel_path(ctx.project_dir, path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            ctx.node_load_errors.append(
                CheckResult(
                    code="node/io_error",
                    severity="error",
                    file=rel,
                    message=f"Could not read file: {exc}",
                )
            )
            continue
        try:
            frontmatter, body = parse_frontmatter_body(text)
        except ParseError as exc:
            ctx.node_load_errors.append(
                CheckResult(
                    code="node/parse_error",
                    severity="error",
                    file=rel,
                    message=str(exc),
                    fix_hint=(
                        "Check the frontmatter delimiters (`---`) and YAML syntax."
                    ),
                )
            )
            continue
        try:
            model = ConceptNode.model_validate({**frontmatter, "body": body})
        except ValueError as exc:
            ctx.node_load_errors.append(
                CheckResult(
                    code="node/schema_invalid",
                    severity="error",
                    file=rel,
                    message=f"Schema validation failed: {exc}",
                    fix_hint=(
                        "Check the field types and required fields for "
                        "ConceptNode. Compare against the example file "
                        "in .claude/skills/project-manager/examples/."
                    ),
                )
            )
            continue
        ctx.nodes.append(
            LoadedEntity(
                rel_path=rel, raw_frontmatter=frontmatter, body=body, model=model
            )
        )


def _load_sessions(ctx: ValidationContext) -> None:
    """Load every session at `sessions/<id>/session.yaml`.

    Walks each subdirectory of `sessions/` instead of globbing `*.yaml`
    at the top level (which would miss the directory layout and silently
    skip every session, as was the case before Phase 3).
    """
    sessions_root = paths.sessions_dir(ctx.project_dir)
    if not sessions_root.is_dir():
        return
    for sdir in sorted(p for p in sessions_root.iterdir() if p.is_dir()):
        if sdir.name.startswith("."):
            continue
        yaml_path = sdir / paths.SESSION_FILENAME
        rel = _rel_path(ctx.project_dir, yaml_path)
        if not yaml_path.is_file():
            ctx.session_load_errors.append(
                CheckResult(
                    code="session/no_session_yaml",
                    severity="error",
                    file=rel,
                    message=(
                        f"Session directory {sdir.name!r} has no "
                        f"{paths.SESSION_FILENAME}. Each session must have "
                        f"a YAML file at that path."
                    ),
                )
            )
            continue
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except OSError as exc:
            ctx.session_load_errors.append(
                CheckResult(
                    code="session/io_error",
                    severity="error",
                    file=rel,
                    message=f"Could not read file: {exc}",
                )
            )
            continue
        try:
            frontmatter, body = parse_frontmatter_body(text)
        except ParseError as exc:
            ctx.session_load_errors.append(
                CheckResult(
                    code="session/parse_error",
                    severity="error",
                    file=rel,
                    message=str(exc),
                    fix_hint=(
                        "Check the frontmatter delimiters (`---`) and YAML syntax."
                    ),
                )
            )
            continue
        try:
            model = AgentSession.model_validate({**frontmatter, "body": body})
        except ValueError as exc:
            ctx.session_load_errors.append(
                CheckResult(
                    code="session/schema_invalid",
                    severity="error",
                    file=rel,
                    message=f"Schema validation failed: {exc}",
                    fix_hint=(
                        "Check the field types and required fields for "
                        "AgentSession. Compare against the example file "
                        "in .claude/skills/project-manager/examples/."
                    ),
                )
            )
            continue
        ctx.sessions.append(
            LoadedEntity(
                rel_path=rel, raw_frontmatter=frontmatter, body=body, model=model
            )
        )


def _load_issues(ctx: ValidationContext) -> None:
    """Load every issue at `issues/<KEY>/issue.yaml`.

    Walks each subdirectory of `issues/` so per-issue comments and
    developer notes can live alongside the spec. Mirrors `_load_sessions`.
    """
    issues_root = paths.issues_dir(ctx.project_dir)
    if not issues_root.is_dir():
        return
    for idir in sorted(p for p in issues_root.iterdir() if p.is_dir()):
        if idir.name.startswith("."):
            continue
        yaml_path = idir / paths.ISSUE_FILENAME
        rel = _rel_path(ctx.project_dir, yaml_path)
        if not yaml_path.is_file():
            ctx.issue_load_errors.append(
                CheckResult(
                    code="issue/no_issue_yaml",
                    severity="error",
                    file=rel,
                    message=(
                        f"Issue directory {idir.name!r} has no "
                        f"{paths.ISSUE_FILENAME}. Each issue must have a "
                        f"YAML file at that path."
                    ),
                )
            )
            continue
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except OSError as exc:
            ctx.issue_load_errors.append(
                CheckResult(
                    code="issue/io_error",
                    severity="error",
                    file=rel,
                    message=f"Could not read file: {exc}",
                )
            )
            continue
        try:
            frontmatter, body = parse_frontmatter_body(text)
        except ParseError as exc:
            ctx.issue_load_errors.append(
                CheckResult(
                    code="issue/parse_error",
                    severity="error",
                    file=rel,
                    message=str(exc),
                    fix_hint=(
                        "Check the frontmatter delimiters (`---`) and YAML syntax."
                    ),
                )
            )
            continue
        try:
            model = Issue.model_validate({**frontmatter, "body": body})
        except ValueError as exc:
            ctx.issue_load_errors.append(
                CheckResult(
                    code="issue/schema_invalid",
                    severity="error",
                    file=rel,
                    message=f"Schema validation failed: {exc}",
                    fix_hint=(
                        "Check the field types and required fields for "
                        "Issue. Compare against the example file in "
                        ".claude/skills/project-manager/examples/."
                    ),
                )
            )
            continue
        ctx.issues.append(
            LoadedEntity(
                rel_path=rel, raw_frontmatter=frontmatter, body=body, model=model
            )
        )


def _load_comments(ctx: ValidationContext) -> None:
    """Comments live under `issues/<KEY>/comments/<filename>.yaml`."""
    issues_root = paths.issues_dir(ctx.project_dir)
    if not issues_root.is_dir():
        return
    for issue_dir in sorted(p for p in issues_root.iterdir() if p.is_dir()):
        comments_dir = issue_dir / paths.COMMENTS_SUBDIR
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
    _load_issues(ctx)
    _load_nodes(ctx)
    _load_sessions(ctx)
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

REQUIRED_EPIC_BODY_HEADINGS = (
    "Context",
    "Child issues",
    "Acceptance criteria",
)


def _is_epic(issue: Any) -> bool:
    """Return True if the issue has a ``type/epic`` label."""
    return any(label == "type/epic" for label in getattr(issue, "labels", []))


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
                            f"Create {paths.NODES_DIR}/{ref}.yaml or fix the "
                            f"reference. Existing nodes: {sorted(node_ids)[:5]}..."
                            if node_ids
                            else f"Create {paths.NODES_DIR}/{ref}.yaml or fix the reference."
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
    agents_dir = project_dir / paths.AGENTS_DIR
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
    """Required Markdown headings, acceptance checkbox, stop-and-ask, refs count.

    Epics (issues with ``type/epic`` label) have relaxed requirements:
    only Context, Child issues, and Acceptance criteria headings are
    required, and stop-and-ask guidance is not checked.
    """
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        body = issue.body
        epic = _is_epic(issue)
        required_headings = (
            REQUIRED_EPIC_BODY_HEADINGS if epic else REQUIRED_ISSUE_BODY_HEADINGS
        )

        for heading in required_headings:
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

        # Stop-and-ask guidance — not required for epics (they are not
        # executed by agents, so ambiguity guidance is irrelevant).
        if (
            not epic
            and "stop and ask" not in body.lower()
            and "stop, ask" not in body.lower()
        ):
            results.append(
                CheckResult(
                    code="body/no_stop_and_ask",
                    severity="warning",
                    file=entity.rel_path,
                    field="body",
                    message="Issue body is missing 'stop and ask' guidance for ambiguity.",
                )
            )

        # Node references — warning for both epics and concrete issues,
        # but epics are less likely to reference code-level nodes.
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
        rel = rel_by_id.get(fr.node_id, f"{paths.NODES_DIR}/{fr.node_id}.yaml")
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
                    fix_hint="Run `tripwire node check --update` (deferred to a later release).",
                )
            )
    return results


def _load_manifest(
    ctx: ValidationContext,
) -> tuple[ArtifactManifest | None, list[CheckResult]]:
    """Parse `templates/artifacts/manifest.yaml` via the Pydantic model.

    Returns (manifest, findings). A missing manifest file is not an error
    (returns `(None, [])`). YAML parse errors and schema violations — including
    unknown `produced_by` / `owned_by` agent types — surface as
    `manifest_schema/*` findings so `check_manifest_schema` can emit them.
    """
    manifest_path = paths.templates_artifacts_manifest_path(ctx.project_dir)
    if not manifest_path.exists():
        return None, []
    rel = paths.TEMPLATES_ARTIFACTS_MANIFEST
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return None, [
            CheckResult(
                code="manifest_schema/parse_error",
                severity="error",
                file=rel,
                message=f"manifest.yaml failed to parse: {exc}",
            )
        ]
    try:
        manifest = ArtifactManifest.model_validate(raw)
    except ValidationError as exc:
        findings: list[CheckResult] = []
        for err in exc.errors():
            loc = err.get("loc", ())
            field_name = loc[-1] if loc else None
            code = "manifest_schema/invalid"
            if field_name == "produced_by":
                code = "manifest_schema/produced_by_valid"
            elif field_name == "owned_by":
                code = "manifest_schema/owned_by_valid"
            findings.append(
                CheckResult(
                    code=code,
                    severity="error",
                    file=rel,
                    field=str(field_name) if field_name is not None else None,
                    message=err.get("msg", "manifest.yaml failed schema validation."),
                )
            )
        return None, findings
    return manifest, []


def check_manifest_schema(ctx: ValidationContext) -> list[CheckResult]:
    """`templates/artifacts/manifest.yaml` parses and matches the schema.

    Emits `manifest_schema/produced_by_valid` or `manifest_schema/owned_by_valid`
    when those enum-like fields carry an unknown agent type.
    """
    _, findings = _load_manifest(ctx)
    return findings


def check_manifest_phase_ownership_consistent(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """Warn if pm owns an artifact produced during implementing/verifying.

    The PM agent steers scoping and planning; once a session is in
    `implementing` or `verifying`, the execution/verification agent owns
    what gets written. A manifest that assigns `owned_by: pm` to such
    artifacts likely encodes the v0.5 bug where the PM wrote files the
    execution agent should have written.
    """
    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []
    results: list[CheckResult] = []
    for entry in manifest.artifacts:
        if entry.owned_by == "pm" and entry.produced_at in (
            "implementing",
            "verifying",
        ):
            results.append(
                CheckResult(
                    code="manifest_schema/phase_ownership_consistent",
                    severity="warning",
                    file=paths.TEMPLATES_ARTIFACTS_MANIFEST,
                    field="owned_by",
                    message=(
                        f"artifact '{entry.name}' owned by pm but produced at "
                        f"{entry.produced_at} — consider ownership by "
                        "execution-agent or verification-agent"
                    ),
                )
            )
    return results


def check_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Sessions in `completed` status must have all required artifacts."""
    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []
    required_files = [a.file for a in manifest.artifacts if a.required]

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != "completed":
            continue
        artifacts_dir = paths.session_artifacts_dir(ctx.project_dir, session.id)
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
                        fix_hint=(
                            f"Write {paths.SESSIONS_DIR}/{session.id}/"
                            f"{paths.SESSION_ARTIFACTS_SUBDIR}/{artifact_file}."
                        ),
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
    standards_path = ctx.project_dir / paths.STANDARDS
    referenced = False
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions):
        for entity in bucket:
            if paths.STANDARDS in entity.body:
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
    from tripwire.core.parser import serialize_frontmatter_body

    abs_path = project_dir / entity.rel_path
    text = serialize_frontmatter_body(entity.raw_frontmatter, entity.body)
    abs_path.write_text(text, encoding="utf-8")


def apply_fixes(ctx: ValidationContext) -> list[CheckResult]:
    """Apply the auto-fix subset and return a list of fix CheckResults.

    Serialised across concurrent invocations by `project_lock`: two
    `tripwire validate --fix` calls can't interleave their writes and lose
    each other's changes. Bidirectional-ref fixes can write multiple
    files in one batch, so a single lock covers the whole transaction.
    """
    try:
        with project_lock(ctx.project_dir):
            return _apply_fixes_locked(ctx)
    except LockTimeout as exc:
        # Return a single fix result describing the failure so callers
        # can surface it; don't silently skip fixes.
        return [
            CheckResult(
                code="fix/lock_timeout",
                severity="error",
                file=None,
                message=str(exc),
            )
        ]


def _apply_fixes_locked(ctx: ValidationContext) -> list[CheckResult]:
    """Apply every auto-fix under the assumption that the project lock
    is already held. Extracted so `apply_fixes` stays a thin wrapper."""
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

    # Invalidate the graph cache for every file we touched so a subsequent
    # read inside the same process sees the new state. Comments and
    # sessions are no-ops (graph_cache._classify ignores them).
    if dirty:
        from tripwire.core.graph_cache import update_cache_for_file

        for rel in dirty:
            update_cache_for_file(ctx.project_dir, rel)

    return fixes


def _filter_none(items: list[Any]) -> list[Any]:
    return [i for i in items if i is not None]


# ============================================================================
# v0.2 checks — UUID v4 + coverage heuristics
# ============================================================================


def check_uuid_v4_version(ctx: ValidationContext) -> list[CheckResult]:
    """Check that UUIDs have RFC 4122 version 4 bits set."""
    results: list[CheckResult] = []
    for _bucket_name, bucket in [
        ("issue", ctx.issues),
        ("node", ctx.nodes),
        ("session", ctx.sessions),
    ]:
        for entity in bucket:
            uid = entity.raw_frontmatter.get("uuid")
            if uid is None:
                continue
            uid_str = str(uid).replace("-", "")
            if len(uid_str) != 32:
                continue
            # Version nibble (char 12, 0-indexed) must be '4'
            version_char = uid_str[12]
            # Variant nibble (char 16) must be 8, 9, a, or b
            variant_char = uid_str[16]
            if version_char != "4" or variant_char not in "89ab":
                results.append(
                    CheckResult(
                        code="uuid/not_v4",
                        severity="error",
                        file=entity.rel_path,
                        field="uuid",
                        message=(
                            f"UUID {uid} is not a valid RFC 4122 v4 UUID. "
                            f"Use `tripwire uuid` to generate real UUIDs."
                        ),
                        fix_hint="Run `tripwire uuid` and replace the value.",
                    )
                )
    return results


def check_coverage_heuristics(ctx: ValidationContext) -> list[CheckResult]:
    """Coverage warnings — hint at potential semantic gaps."""
    results: list[CheckResult] = []

    # Build reference counts from issue bodies
    node_ids = {e.raw_frontmatter.get("id", "") for e in ctx.nodes}
    node_ref_counts: dict[str, int] = dict.fromkeys(node_ids, 0)

    for entity in ctx.issues:
        refs = extract_references(entity.body)
        issue_has_node_ref = False
        for ref in refs:
            if ref in node_ref_counts:
                node_ref_counts[ref] += 1
                issue_has_node_ref = True
        if not issue_has_node_ref and entity.body.strip():
            results.append(
                CheckResult(
                    code="coverage/no_nodes_referenced",
                    severity="warning",
                    file=entity.rel_path,
                    message=(
                        "Issue body contains no [[node-id]] references. "
                        "Consider linking to relevant concept nodes."
                    ),
                )
            )

    for nid, count in node_ref_counts.items():
        if count <= 1 and nid:
            node_entity = next(
                (e for e in ctx.nodes if e.raw_frontmatter.get("id") == nid),
                None,
            )
            if node_entity:
                results.append(
                    CheckResult(
                        code="coverage/unreferenced_node",
                        severity="warning",
                        file=node_entity.rel_path,
                        message=(
                            f"Concept node '{nid}' is referenced by only "
                            f"{count} issue(s). Consider whether other issues "
                            f"should reference it, or merge it."
                        ),
                    )
                )

    return results


# ============================================================================
# Phase-aware validation
# ============================================================================

# Scoping-phase artifacts and their required status marker.
_SCOPING_PLAN_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/scoping-plan.md"
_GAP_ANALYSIS_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/gap-analysis.md"
_COMPLIANCE_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/compliance.md"


def _artifact_status(project_dir: Path, rel_path: str) -> str | None:
    """Return the status marker from a meta-artifact, or None if missing.

    Artifacts use a ``<!-- status: complete -->`` HTML comment on any line
    to signal completion.  Returns ``"complete"``, ``"incomplete"``, or
    ``None`` (file doesn't exist or is empty).
    """
    full = project_dir / rel_path
    if not full.is_file():
        return None
    text = full.read_text(encoding="utf-8").strip()
    if not text:
        return None
    if "<!-- status: complete -->" in text:
        return "complete"
    return "incomplete"


def check_phase_requirements(ctx: ValidationContext) -> list[CheckResult]:
    """Enforce phase-specific requirements.

    - **scoping**: ``scoping-plan.md`` must exist.
    - **scoped**: ``gap-analysis.md`` and ``compliance.md`` must exist
      and be marked ``complete``.  All sessions must have ``plan.md``.
    - **executing** / **reviewing**: same as scoped.
    """
    from tripwire.models.project import ProjectPhase

    if ctx.project_config is None:
        return []

    phase = ctx.project_config.phase
    results: list[CheckResult] = []

    # --- scoping: scoping-plan.md expected once entities exist ---------
    if phase == ProjectPhase.scoping and ctx.issues:
        status = _artifact_status(ctx.project_dir, _SCOPING_PLAN_PATH)
        if status is None:
            results.append(
                CheckResult(
                    code="phase/missing_artifact",
                    severity="warning",
                    file=_SCOPING_PLAN_PATH,
                    message=(
                        "Issues exist but no scoping plan found. "
                        "Write the scoping plan before creating entities."
                    ),
                )
            )

    # --- scoped and beyond: gap-analysis + compliance required --------
    if phase in (
        ProjectPhase.scoped,
        ProjectPhase.executing,
        ProjectPhase.reviewing,
    ):
        for artifact_path, label in (
            (_GAP_ANALYSIS_PATH, "gap analysis"),
            (_COMPLIANCE_PATH, "compliance checklist"),
        ):
            status = _artifact_status(ctx.project_dir, artifact_path)
            if status is None:
                results.append(
                    CheckResult(
                        code="phase/missing_artifact",
                        severity="error",
                        file=artifact_path,
                        message=(
                            f"Phase '{phase.value}' requires {artifact_path}. "
                            f"Complete the {label} before advancing to this phase."
                        ),
                    )
                )
            elif status == "incomplete":
                results.append(
                    CheckResult(
                        code="phase/incomplete_artifact",
                        severity="error",
                        file=artifact_path,
                        message=(
                            f"{artifact_path} exists but is not marked complete. "
                            f"Add '<!-- status: complete -->' when finished."
                        ),
                    )
                )

        # All sessions must have plan.md. Iterate ctx.sessions (loaded by
        # _load_sessions) instead of re-globbing the filesystem.
        for entity in ctx.sessions:
            session: AgentSession = entity.model
            plan = paths.session_plan_path(ctx.project_dir, session.id)
            if not plan.is_file():
                results.append(
                    CheckResult(
                        code="phase/missing_session_plan",
                        severity="error",
                        file=(
                            f"{paths.SESSIONS_DIR}/{session.id}/{paths.SESSION_PLAN}"
                        ),
                        message=(
                            f"Session {session.id!r} has no "
                            f"{paths.SESSION_PLAN}. All sessions must have "
                            f"plans before phase '{phase.value}'."
                        ),
                    )
                )

    return results


# ============================================================================
# Handoff artifact (v0.6a)
# ============================================================================


def check_handoff_artifact(ctx: ValidationContext) -> list[CheckResult]:
    """v0.6a: sessions in ``queued`` state require a valid handoff.yaml.

    Three possible findings:
    - ``handoff_schema/required_at_queued`` — session queued but file missing.
    - ``handoff_schema/branch_format`` — handoff.yaml.branch violates
      the ``<type>/<slug>`` convention (extracted via raw YAML parse so
      malformed branches surface cleanly, not as generic schema errors).
    - ``handoff_schema/malformed`` — any other parse/schema failure.
    """
    results: list[CheckResult] = []

    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != "queued":
            continue

        handoff_file_rel = f"{paths.SESSIONS_DIR}/{session.id}/{paths.HANDOFF_FILENAME}"
        handoff_file = paths.handoff_path(ctx.project_dir, session.id)
        if not handoff_file.is_file():
            results.append(
                CheckResult(
                    code="handoff_schema/required_at_queued",
                    severity="error",
                    file=handoff_file_rel,
                    message=(
                        f"Session {session.id!r} is queued but handoff.yaml "
                        "is missing — launch requires a structured handoff "
                        "artifact."
                    ),
                    fix_hint=(
                        "Run `/pm-session-queue` which creates handoff.yaml, "
                        "or write sessions/<id>/handoff.yaml manually."
                    ),
                )
            )
            continue

        # Check branch format via raw YAML parse first so malformed branch
        # strings surface as handoff_schema/branch_format (the specific code
        # callers expect), not as a generic Pydantic ValidationError.
        try:
            text = handoff_file.read_text(encoding="utf-8")
            frontmatter, _body = parse_frontmatter_body(text)
        except (ParseError, OSError) as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml failed to parse: {exc}",
                )
            )
            continue

        branch = frontmatter.get("branch") if isinstance(frontmatter, dict) else None
        if isinstance(branch, str):
            from tripwire.core.branch_naming import is_valid_branch_name

            if not is_valid_branch_name(branch):
                results.append(
                    CheckResult(
                        code="handoff_schema/branch_format",
                        severity="error",
                        file=handoff_file_rel,
                        field="branch",
                        message=(
                            f"handoff.yaml.branch {branch!r} does not match "
                            "the <type>/<slug> convention."
                        ),
                        fix_hint=(
                            "Run `tripwire session derive-branch <session-id>` "
                            "and copy its output."
                        ),
                    )
                )
                continue

        # Pydantic validation catches any other schema problems (missing
        # required fields, bad types). The branch validator inside
        # SessionHandoff raises the same branch-format error, but this
        # function already handled that code above, so any ValidationError
        # here is structural.
        try:
            from tripwire.core.handoff_store import load_handoff

            load_handoff(ctx.project_dir, session.id)
        except ValidationError as exc:
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=f"handoff.yaml schema validation failed: {exc}",
                )
            )
        except ValueError as exc:
            # branch format (caught again via SessionHandoff validator) or
            # unparseable YAML.
            results.append(
                CheckResult(
                    code="handoff_schema/malformed",
                    severity="error",
                    file=handoff_file_rel,
                    message=str(exc),
                )
            )

    return results


# ============================================================================
# Quality consistency (anti-fatigue)
# ============================================================================

# Thresholds for flagging output degradation across a writing session.
# These detect *inconsistency*, not absolute shortness — a project where
# all issues are 1,200 chars is fine; one where early issues are 2,500
# and late ones are 1,500 is flagged.
QUALITY_BODY_DEGRADATION_THRESHOLD = 0.20  # 20% drop → warning
QUALITY_REF_DEGRADATION_THRESHOLD = 0.40  # 40% drop → warning
QUALITY_MIN_ISSUES_FOR_CHECK = 9  # need 3+ per third


def check_quality_consistency(ctx: ValidationContext) -> list[CheckResult]:
    """Detect quality degradation across a writing session.

    Sorts concrete issues by key number (proxy for creation order),
    splits into first-third and last-third, and compares average body
    length and reference count.  Warns when the last-third is
    significantly thinner than the first — the "fatigue pattern" where
    agent output degrades over time.
    """
    results: list[CheckResult] = []

    # Collect concrete issues with parseable keys
    concrete: list[tuple[int, LoadedEntity]] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if _is_epic(issue):
            continue
        try:
            _prefix, num = parse_key(issue.id)
            concrete.append((num, entity))
        except (ValueError, AttributeError):
            continue

    if len(concrete) < QUALITY_MIN_ISSUES_FOR_CHECK:
        return results

    # Sort by key number (creation order proxy)
    concrete.sort(key=lambda x: x[0])
    third = len(concrete) // 3

    first_third = concrete[:third]
    last_third = concrete[-third:]

    # --- Body character comparison ---
    first_avg_chars = sum(len(e.body) for _, e in first_third) / len(first_third)
    last_avg_chars = sum(len(e.body) for _, e in last_third) / len(last_third)

    if first_avg_chars > 0:
        body_drop = (first_avg_chars - last_avg_chars) / first_avg_chars
        if body_drop > QUALITY_BODY_DEGRADATION_THRESHOLD:
            results.append(
                CheckResult(
                    code="quality/body_degradation",
                    severity="warning",
                    message=(
                        f"Issue body quality degrades over the session. "
                        f"First-third concrete issues average {first_avg_chars:.0f} chars; "
                        f"last-third average {last_avg_chars:.0f} chars "
                        f"({body_drop:.0%} shorter). "
                        f"Reread and expand later issues to match the depth of earlier ones."
                    ),
                    fix_hint=(
                        "Run the quality calibration checkpoint: reread your first 3 "
                        "and last 3 concrete issues, rewrite the last 3 if thinner."
                    ),
                )
            )

    # --- Reference count comparison ---
    first_avg_refs = sum(
        len(set(extract_references(e.body))) for _, e in first_third
    ) / len(first_third)
    last_avg_refs = sum(
        len(set(extract_references(e.body))) for _, e in last_third
    ) / len(last_third)

    if first_avg_refs > 0:
        ref_drop = (first_avg_refs - last_avg_refs) / first_avg_refs
        if ref_drop > QUALITY_REF_DEGRADATION_THRESHOLD:
            results.append(
                CheckResult(
                    code="quality/ref_degradation",
                    severity="warning",
                    message=(
                        f"Node reference density degrades over the session. "
                        f"First-third concrete issues average {first_avg_refs:.1f} "
                        f"unique [[refs]]; last-third average {last_avg_refs:.1f} "
                        f"({ref_drop:.0%} fewer). "
                        f"Add missing [[node-id]] references to later issues."
                    ),
                    fix_hint=(
                        "Run the quality calibration checkpoint: reread your first 3 "
                        "and last 3 concrete issues, rewrite the last 3 if thinner."
                    ),
                )
            )

    return results


# ============================================================================
# The main entry point
# ============================================================================


ALL_CHECKS = [
    check_uuid_present,
    check_uuid_v4_version,
    check_id_format,
    check_enum_values,
    check_reference_integrity,
    check_bidirectional_related,
    check_issue_body_structure,
    check_status_transitions,
    check_freshness,
    check_manifest_schema,
    check_manifest_phase_ownership_consistent,
    check_artifact_presence,
    check_id_collisions,
    check_sequence_drift,
    check_timestamps,
    check_comment_provenance,
    check_project_standards,
    check_coverage_heuristics,
    check_phase_requirements,
    check_handoff_artifact,
    check_quality_consistency,
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
    from tripwire.core import graph_cache

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
