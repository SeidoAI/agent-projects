"""Merge brief generator and store.

A merge brief is a structured YAML file written to
``<project>/.keel/merge-briefs/<node-id>.yaml`` when a 3-way merge
surfaces non-trivial conflicts. The PM agent reads the brief, edits
the node file to a resolved form, and runs ``keel workspace
merge-resolve`` to finalize.

Bookkeeping fields (uuid, created_at, updated_at, origin, scope,
workspace_sha, workspace_pulled_at) are excluded from ``field_diffs``
and hint generation — they describe the pull, not the content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml

from keel.core.paths import merge_brief_path, merge_briefs_dir
from keel.core.workspace_sync import EXCLUDED_FROM_MERGE


class MergeType(Enum):
    PULL = "pull"
    PUSH = "push"


FieldDiffStatus = Literal["ours_only", "theirs_only", "conflict", "structural"]


@dataclass
class FieldDiff:
    field: str
    base: Any
    ours: Any
    theirs: Any
    status: FieldDiffStatus


@dataclass
class MergeBrief:
    node_id: str
    merge_type: MergeType
    base_sha: str
    generated_at: datetime
    base_version: dict[str, Any]
    ours_version: dict[str, Any]
    theirs_version: dict[str, Any]
    field_diffs: list[FieldDiff]
    auto_merged_fields: list[str]
    hints: list[str] = field(default_factory=list)


def build_merge_brief(
    *,
    node_id: str,
    merge_type: MergeType,
    base_sha: str,
    base: dict,
    ours: dict,
    theirs: dict,
    auto_merged_fields: list[str] | None = None,
) -> MergeBrief:
    """Construct a MergeBrief from the three versions.

    Produces a ``field_diffs`` list for every non-bookkeeping field
    where at least one of (base, ours, theirs) differs, plus
    plain-language hints for conflict fields to help the agent reason.
    """
    diffs: list[FieldDiff] = []
    all_keys = (set(base) | set(ours) | set(theirs)) - EXCLUDED_FROM_MERGE

    for key in sorted(all_keys):
        b = base.get(key)
        o = ours.get(key)
        t = theirs.get(key)
        if b == o == t:
            continue
        if o == t:
            # Both sides applied the same change (either as structural
            # edits or no-op). Classify as structural — non-blocking.
            status: FieldDiffStatus = "structural"
        elif o == b:
            status = "theirs_only"
        elif t == b:
            status = "ours_only"
        else:
            status = "conflict"
        diffs.append(FieldDiff(field=key, base=b, ours=o, theirs=t, status=status))

    return MergeBrief(
        node_id=node_id,
        merge_type=merge_type,
        base_sha=base_sha,
        generated_at=datetime.now(tz=timezone.utc),
        base_version=base,
        ours_version=ours,
        theirs_version=theirs,
        field_diffs=diffs,
        auto_merged_fields=auto_merged_fields or [],
        hints=_generate_hints(diffs),
    )


def _generate_hints(diffs: list[FieldDiff]) -> list[str]:
    """Plain-language guidance for fields in conflict."""
    hints: list[str] = []
    for d in diffs:
        if d.status != "conflict":
            continue
        if isinstance(d.ours, str) and isinstance(d.theirs, str):
            hints.append(
                f"field `{d.field}`: both sides modified the text. Consider "
                "whether the changes are additive (combine them) or truly "
                "contradictory (pick one based on project intent)."
            )
        elif isinstance(d.ours, list) and isinstance(d.theirs, list):
            hints.append(
                f"field `{d.field}`: both sides modified the list. Union may "
                "be the right answer if the additions are independent."
            )
        else:
            hints.append(
                f"field `{d.field}`: typed conflict — examine base/ours/theirs "
                "and pick one. If the types differ, consider forking."
            )
    if not hints and diffs:
        hints.append(
            "Non-overlapping field changes present — review each entry's "
            "`status` and accept base/ours/theirs per field."
        )
    return hints


# ============================================================================
# Persistence
# ============================================================================


def save_merge_brief(project_dir: Path, brief: MergeBrief) -> None:
    merge_briefs_dir(project_dir).mkdir(parents=True, exist_ok=True)
    data = {
        "node_id": brief.node_id,
        "merge_type": brief.merge_type.value,
        "base_sha": brief.base_sha,
        "generated_at": brief.generated_at.isoformat(),
        "base_version": _yaml_safe(brief.base_version),
        "ours_version": _yaml_safe(brief.ours_version),
        "theirs_version": _yaml_safe(brief.theirs_version),
        "field_diffs": [
            {
                "field": d.field,
                "base": _yaml_safe(d.base),
                "ours": _yaml_safe(d.ours),
                "theirs": _yaml_safe(d.theirs),
                "status": d.status,
            }
            for d in brief.field_diffs
        ],
        "auto_merged_fields": brief.auto_merged_fields,
        "hints": brief.hints,
    }
    merge_brief_path(project_dir, brief.node_id).write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )


def load_merge_brief(project_dir: Path, node_id: str) -> MergeBrief | None:
    path = merge_brief_path(project_dir, node_id)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return MergeBrief(
        node_id=data["node_id"],
        merge_type=MergeType(data["merge_type"]),
        base_sha=data["base_sha"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
        base_version=data["base_version"],
        ours_version=data["ours_version"],
        theirs_version=data["theirs_version"],
        field_diffs=[FieldDiff(**d) for d in data["field_diffs"]],
        auto_merged_fields=data.get("auto_merged_fields", []),
        hints=data.get("hints", []),
    )


def delete_merge_brief(project_dir: Path, node_id: str) -> None:
    path = merge_brief_path(project_dir, node_id)
    if path.exists():
        path.unlink()


def list_pending_briefs(project_dir: Path) -> list[str]:
    """Return sorted node ids that have pending merge briefs."""
    d = merge_briefs_dir(project_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def _yaml_safe(value: Any) -> Any:
    """Recursively coerce types yaml.safe_dump can't handle into portable forms."""
    from uuid import UUID as _UUID

    if isinstance(value, dict):
        return {k: _yaml_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_yaml_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_yaml_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, _UUID):
        return str(value)
    return value
