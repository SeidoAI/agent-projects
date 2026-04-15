"""Three-way merge engine for workspace-origin nodes.

Compares base (workspace at last_pulled_sha), ours (current project
copy), and theirs (current workspace HEAD). Returns a MergeResult
with a status and either a merged dict (trivial cases) or a
conflicting_fields list (non-trivial — handled by merge brief).

Bookkeeping fields (``uuid``, ``created_at``, ``updated_at``,
``origin``, ``scope``, ``workspace_sha``, ``workspace_pulled_at``)
are excluded from the merge diff — they describe the *pull*, not the
node's content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

EXCLUDED_FROM_MERGE: frozenset[str] = frozenset(
    {
        "uuid",
        "created_at",
        "updated_at",
        "origin",
        "scope",
        "workspace_sha",
        "workspace_pulled_at",
    }
)


class MergeStatus(Enum):
    NO_CHANGES = "no_changes"  # ours == base == theirs
    NO_UPSTREAM_CHANGES = "no_upstream"  # theirs == base, keep ours
    FAST_FORWARD = "fast_forward"  # ours == base, take theirs
    AUTO_MERGED = "auto_merged"  # non-overlapping changes
    CONFLICT = "conflict"  # overlapping changes, need agent


@dataclass
class MergeResult:
    status: MergeStatus
    merged: dict[str, Any] | None = None  # populated for non-CONFLICT
    conflicting_fields: list[str] = field(default_factory=list)
    auto_merged_fields: list[str] = field(default_factory=list)


def _normalize(d: dict) -> dict:
    """Drop bookkeeping + fields that are absent-equivalent.

    Treats as equivalent to "missing":
    - ``None``
    - ``""`` (empty string — Pydantic defaults Issue.body etc. to "")
    - ``[]`` (empty list — Pydantic defaults `related`, `tags` to [])
    - ``{}`` (empty dict)

    This lets Pydantic-hydrated dicts compare equal to raw YAML frontmatter
    dicts that simply omit unused fields.
    """
    out: dict = {}
    for k, v in d.items():
        if k in EXCLUDED_FROM_MERGE:
            continue
        if v is None or v == "" or v == [] or v == {}:
            continue
        out[k] = v
    return out


def _content_equal(a: dict, b: dict) -> bool:
    """Dict equality ignoring bookkeeping fields and absent/None/[] gaps."""
    return _normalize(a) == _normalize(b)


def merge_nodes(
    *, base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
) -> MergeResult:
    """Three-way merge two node dicts against their common ancestor.

    On CONFLICT the ``merged`` dict is None and callers should generate
    a merge brief from (base, ours, theirs). For all other statuses
    ``merged`` contains a dict ready to be written back with fresh
    bookkeeping applied by the caller.
    """
    if _content_equal(ours, base):
        if _content_equal(theirs, base):
            return MergeResult(status=MergeStatus.NO_CHANGES, merged=dict(theirs))
        return MergeResult(status=MergeStatus.FAST_FORWARD, merged=dict(theirs))

    if _content_equal(theirs, base):
        return MergeResult(
            status=MergeStatus.NO_UPSTREAM_CHANGES, merged=dict(ours)
        )

    # Both sides diverged from base. Check field-by-field.
    all_keys = (set(base) | set(ours) | set(theirs)) - EXCLUDED_FROM_MERGE

    merged: dict[str, Any] = dict(base)
    # Carry bookkeeping fields forward from ours by default; caller
    # overrides workspace_sha etc. based on operation type.
    for key in EXCLUDED_FROM_MERGE:
        if key in ours:
            merged[key] = ours[key]

    conflicting: list[str] = []
    auto: list[str] = []

    for key in sorted(all_keys):
        b = base.get(key)
        o = ours.get(key)
        t = theirs.get(key)
        if o == t:
            merged[key] = o
            if o != b:
                auto.append(key)
            continue
        if o == b:
            merged[key] = t
            auto.append(key)
        elif t == b:
            merged[key] = o
            auto.append(key)
        else:
            conflicting.append(key)

    if conflicting:
        return MergeResult(
            status=MergeStatus.CONFLICT,
            merged=None,
            conflicting_fields=conflicting,
            auto_merged_fields=auto,
        )
    return MergeResult(
        status=MergeStatus.AUTO_MERGED,
        merged=merged,
        auto_merged_fields=auto,
    )
