"""The validation gate.

`tripwire validate` is the single most important command in the system.
This module implements the engine: load every entity, run every check in the
catalogue, optionally apply auto-fixes, and emit a structured report.

The check catalogue (matches the "The Validation Gate" section of
`tripwire-plan.md` in the tripwire-workspace repo:
https://github.com/SeidoAI/tripwire-workspace/blob/main/docs/tripwire-plan.md):

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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tripwire.core import paths
from tripwire.core.enum_loader import load_enums
from tripwire.core.event_emitter import EventEmitter, NullEmitter
from tripwire.core.id_generator import parse_key
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.core.store import (
    PROJECT_CONFIG_FILENAME,
    ProjectNotFoundError,
    load_project,
)
from tripwire.core.validator._types import (
    CheckResult,
    LoadedEntity,
    ValidationContext,
    ValidationReport,
)

# Check functions live in `validator/checks/<theme>.py`. Re-imported here so
# the historical `from tripwire.core.validator import check_*` import paths
# keep resolving (and so tests importing the constants `_SESSION_STATUS_TO_PHASE`
# / `_COHERENCE_MATRIX` keep working).
from tripwire.core.validator.checks.artifacts import (
    _load_manifest,
    check_artifact_presence,
    check_issue_artifact_presence,
    check_manifest_phase_ownership_consistent,
    check_manifest_schema,
)
from tripwire.core.validator.checks.coherence import (
    _COHERENCE_MATRIX,
    _SESSION_STATUS_TO_PHASE,
    check_comment_provenance,
    check_freshness,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
    check_session_issue_coherence,
)
from tripwire.core.validator.checks.enums import check_enum_values
from tripwire.core.validator.checks.identity import (
    check_id_collisions,
    check_id_format,
    check_sequence_drift,
    check_timestamps,
    check_uuid_present,
)
from tripwire.core.validator.checks.quality import (
    check_coverage_heuristics,
    check_phase_requirements,
    check_project_standards,
    check_quality_consistency,
)
from tripwire.core.validator.checks.references import (
    check_bidirectional_related,
    check_reference_integrity,
)
from tripwire.core.validator.checks.structure import (
    REQUIRED_EPIC_BODY_HEADINGS,
    REQUIRED_ISSUE_BODY_HEADINGS,
    check_handoff_artifact,
    check_issue_body_structure,
    check_status_transitions,
)
from tripwire.core.validator.checks.workflow import check_workflow_well_formed
from tripwire.models.comment import Comment
from tripwire.models.issue import Issue
from tripwire.models.node import ConceptNode
from tripwire.models.session import AgentSession

logger = logging.getLogger(__name__)


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
# v0.2 checks — coverage heuristics
# ============================================================================


# ============================================================================
# Phase-aware validation
# ============================================================================

# Scoping-phase artifacts and their required status marker.


# ============================================================================
# Handoff artifact (v0.6a)
# ============================================================================


# ============================================================================
# Quality consistency (anti-fatigue)
# ============================================================================

# Thresholds for flagging output degradation across a writing session.
# These detect *inconsistency*, not absolute shortness — a project where
# all issues are 1,200 chars is fine; one where early issues are 2,500
# and late ones are 1,500 is flagged.


# ============================================================================
# The main entry point
# ============================================================================


# v0.7b Layer-3 coherence matrix — spec §6.4.
#
# Matrix is keyed by *phase* (5 values per spec table), not by the full
# SessionStatus enum. SessionStatus values map to a phase via
# _SESSION_STATUS_TO_PHASE. Session statuses not in the mapping are
# off-lifecycle (failed, paused, abandoned, re_engaged, waiting_for_*)
# and skip coherence checking entirely.
#
# Verdict:
#   "ok"           — aligned
#   "ahead_warn"   — issue later in lifecycle than session; surfaces as
#                    `coherence/issue_status_ahead_of_session` (warning).
#   "behind_error" — issue earlier than session; surfaces as
#                    `coherence/issue_status_lags_session` (error).
#
# Spec §6.4 table:
#   planned      → warn on later
#   in_progress  → warn on later
#   in_review    → error on earlier
#   verified     → error on earlier
#   done         → error on anything else


# v0.7.9 §A9 — project-state lint rules live in ``./lint/`` (one module
# per rule, each exporting ``check``). ``LINT_CHECKS`` collects them so
# they run alongside the in-file ``check_*`` functions.
# Imported at the bottom of this module to avoid a circular dependency
# (lint rules import ``CheckResult`` / ``ValidationContext`` from here).
# ALL_CHECKS is built from themed groupings in `validator/checks/`.
# Each constant there (IDENTITY_CHECKS, ENUM_CHECKS, etc.) groups
# related check functions; the aggregator concatenates them in the
# canonical run order so finding output ordering stays byte-stable.
# The function bodies still live in this file — physical per-file
# extraction is a future cycle.
from tripwire.core.validator.checks import ALL_CHECKS as _THEMED_CHECKS  # noqa: E402
from tripwire.core.validator.lint import LINT_CHECKS  # noqa: E402

ALL_CHECKS = [
    *_THEMED_CHECKS,
    # KUI-89 (§A9) — project-state lint rules under ``./lint/``.
    *LINT_CHECKS,
]


_DEFAULT_VALIDATE_SESSION_ID = "_cli_validate"


def _isoformat_z(dt: datetime) -> str:
    """RFC-3339 / ISO-8601 with `Z` suffix — matches the events spec."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit_check_result(
    *,
    emitter: EventEmitter,
    check_fn: Any,
    results: list[CheckResult],
    session_id: str,
) -> None:
    """Emit one `validator_pass` / `validator_fail` event for *check_fn*.

    Aggregates the check's findings into a single event — a check that
    returns ten findings emits one `validator_fail`, not ten. The
    validator id mirrors `workflow_service`: `v_<slug>` where `<slug>` is
    the function name with the `check_` prefix stripped.

    Reads ``check_fn.__tripwire_workflow_station__`` (set by
    :func:`tripwire.core.workflow.registry.registers_at`) so the
    payload carries the (workflow, station) the check is registered
    against — the runtime gates and drift report consume this. KUI-120
    is the registry-consume contract.
    """
    if isinstance(emitter, NullEmitter):
        return
    slug = check_fn.__name__.removeprefix("check_")
    has_error = any(r.severity == "error" for r in results)
    fired_at = _isoformat_z(datetime.now(timezone.utc))
    kind = "validator_fail" if has_error else "validator_pass"
    event_id = f"evt-{fired_at}-{kind}-{slug}-{session_id}"
    pair = getattr(check_fn, "__tripwire_workflow_station__", None)
    payload: dict[str, Any] = {
        "id": event_id,
        "kind": kind,
        "fired_at": fired_at,
        "session_id": session_id,
        "validator_id": f"v_{slug}",
        "findings": [r.to_json() for r in results],
    }
    if pair is not None:
        payload["workflow"] = pair[0]
        payload["station"] = pair[1]
    try:
        emitter.emit("validator_runs", payload)
    except Exception:
        # Emission must never sink the validator run — log and continue.
        logger.exception("validator emission failed for %s", slug)


def _emit_workflow_event(
    *,
    project_dir: Path,
    check_fn: Any,
    results: list[CheckResult],
    session_id: str,
) -> None:
    """Append one ``validator.run`` row to the workflow events log
    (KUI-123) for *check_fn*.

    Skipped silently if the check has no ``__tripwire_workflow_station__``
    attribute (legacy / unregistered) — the workflow log demands
    ``workflow`` + ``station``. Failures are logged and swallowed; the
    log is best-effort, not load-bearing.
    """
    pair = getattr(check_fn, "__tripwire_workflow_station__", None)
    if pair is None:
        return
    workflow, station = pair
    slug = check_fn.__name__.removeprefix("check_")
    has_error = any(r.severity == "error" for r in results)
    outcome = "fail" if has_error else "pass"
    try:
        from tripwire.core.events.log import emit_event

        emit_event(
            project_dir,
            workflow=workflow,
            instance=session_id,
            station=station,
            event="validator.run",
            details={
                "id": f"v_{slug}",
                "outcome": outcome,
                "findings": len(results),
            },
        )
    except Exception:
        logger.exception("workflow events emission failed for %s", slug)


def validate_project(
    project_dir: Path,
    *,
    strict: bool = False,
    fix: bool = False,
    emitter: EventEmitter | None = None,
    session_id: str | None = None,
) -> ValidationReport:
    """Run the full validation gate against a project.

    The agent's normal mode is `strict=True, fix=False`. The orchestrator may
    call with `fix=True` to apply auto-fixes after the agent has done its
    initial pass.

    Always rebuilds the graph cache (`graph/index.yaml`) as a side effect —
    incrementally if the cache is already up to date, as a full rebuild if
    the cache is missing or corrupt.

    If *emitter* is supplied, one ``validator_runs`` event is emitted per
    `check_*` invocation — `validator_pass` if the check returned no
    findings, `validator_fail` otherwise. *session_id* is required when
    callers want events grouped by session; an unspecified id falls back
    to a CLI sentinel so events still aggregate cleanly. The default
    ``NullEmitter()`` emits nothing, preserving today's batch / unit-test
    behaviour. See `docs/specs/2026-04-26-v08-handoff.md` §1.2, §2.2.
    """
    # Import lazily to avoid a circular import at module load time.
    from tripwire.core import graph_cache

    if emitter is None:
        emitter = NullEmitter()
    sid = session_id or _DEFAULT_VALIDATE_SESSION_ID

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
        _emit_check_result(
            emitter=emitter,
            check_fn=check,
            results=results,
            session_id=sid,
        )
        _emit_workflow_event(
            project_dir=project_dir,
            check_fn=check,
            results=results,
            session_id=sid,
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
    "REQUIRED_EPIC_BODY_HEADINGS",
    "REQUIRED_ISSUE_BODY_HEADINGS",
    "_COHERENCE_MATRIX",
    "_SESSION_STATUS_TO_PHASE",
    "CheckResult",
    "LoadedEntity",
    "ValidationContext",
    "ValidationReport",
    "_load_manifest",
    "apply_fixes",
    "asdict",  # convenience
    "check_artifact_presence",
    "check_bidirectional_related",
    "check_comment_provenance",
    "check_coverage_heuristics",
    "check_enum_values",
    "check_freshness",
    "check_handoff_artifact",
    "check_id_collisions",
    "check_id_format",
    "check_issue_artifact_presence",
    "check_issue_body_structure",
    "check_manifest_phase_ownership_consistent",
    "check_manifest_schema",
    "check_phase_requirements",
    "check_pm_response_covers_self_review",
    "check_pm_response_followups_resolve",
    "check_project_standards",
    "check_quality_consistency",
    "check_reference_integrity",
    "check_sequence_drift",
    "check_session_issue_coherence",
    "check_status_transitions",
    "check_timestamps",
    "check_uuid_present",
    "check_workflow_well_formed",
    "load_context",
    "validate_project",
]
