"""Auto-fix primitives — the *act* surface of the validator pipeline.

Philosophy §3 ("Tripwires are agent-facing") gives the framework two
distinct surfaces:

- Validators **report**. They read state, produce findings, never
  mutate. The whole point of §3 is that agents are unreliable but
  obedient; validators stay reliable by staying passive.
- Agents **act**. They read findings, run CLIs, mutate state.

Until v0.13.1 the auto-fix machinery (UUID synthesis, timestamp
backfill, list sorting, bidirectional-ref repair, sequence-drift
correction) lived inside ``core/validator/__init__.py``. That made
the validator module non-passive — a §3 violation surfaced by the
``test_validator_checks_are_pure_read`` fitness function.

The cleanup moves every mutation primitive here. ``validate_project``
in the validator module still orchestrates "validate then fix then
re-validate" when ``fix=True`` is passed, but the *writes* live in
this module exclusively. The validator module is mutation-free; the
fix module is mutation-aware. The split mirrors §3's
report-vs-act partition.

CLI surface: ``tripwire validate --fix`` still works as before —
``validate_project`` delegates to :func:`apply_fixes` here. A separate
``tripwire fix`` verb may land in a future release; the underlying
machinery is already in its own module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from tripwire.core.id_generator import parse_key
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.store import PROJECT_CONFIG_FILENAME
from tripwire.core.validator._types import (
    CheckResult,
    LoadedEntity,
    ValidationContext,
)
from tripwire.models.node import ConceptNode


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
                            f"Added back-reference {node.id!r} to "
                            f"{other.model.id!r}.related."
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


def _filter_none(items: list[Any]) -> list[Any]:
    return [i for i in items if i is not None]


def apply_fixes(ctx: ValidationContext) -> list[CheckResult]:
    """Apply the auto-fix subset and return a list of fix CheckResults.

    Serialised across concurrent invocations by ``project_lock``: two
    ``tripwire validate --fix`` calls can't interleave their writes and
    lose each other's changes. Bidirectional-ref fixes can write
    multiple files in one batch, so a single lock covers the whole
    transaction.
    """
    try:
        with project_lock(ctx.project_dir):
            return _apply_fixes_locked(ctx)
    except LockTimeout as exc:
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
    is already held. Extracted so ``apply_fixes`` stays a thin wrapper."""
    fixes: list[CheckResult] = []
    dirty: set[str] = set()

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

    for bucket in (ctx.issues, ctx.nodes, ctx.sessions, ctx.comments):
        for entity in bucket:
            if entity.rel_path in dirty:
                _rewrite_entity_file(ctx.project_dir, entity)

    # Invalidate the graph cache for every file we touched so a
    # subsequent read inside the same process sees the new state.
    # Comments and sessions are no-ops (graph_cache._classify ignores
    # them).
    if dirty:
        from tripwire.core.graph.cache import update_cache_for_file

        for rel in dirty:
            update_cache_for_file(ctx.project_dir, rel)

    return fixes


__all__ = ["apply_fixes"]
