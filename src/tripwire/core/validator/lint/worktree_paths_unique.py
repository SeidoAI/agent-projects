"""v0.7.9 §A9 — no two sessions may claim the same worktree path.

Walks every session's ``runtime_state.worktrees[*].worktree_path`` and
flags collisions across distinct sessions. Catches the state where
two sessions race to write into the same physical directory — usually
the symptom of a stale runtime_state record left over from a manual
recovery.

Path comparison normalises via :class:`pathlib.Path` (collapses
duplicate separators, removes trailing slashes) but does not resolve
symlinks — the recorded path is the source of truth, even if the
directory does not exist on the validating machine.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def _normalize(path: str) -> str:
    return str(PurePosixPath(path))


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    by_path: dict[str, set[str]] = defaultdict(set)
    entity_for_session: dict[str, object] = {}
    for entity in ctx.sessions:
        sid = entity.model.id
        entity_for_session.setdefault(sid, entity)
        for wt in entity.model.runtime_state.worktrees:
            by_path[_normalize(wt.worktree_path)].add(sid)

    results: list[CheckResult] = []
    for path, sids in sorted(by_path.items()):
        if len(sids) < 2:
            continue
        sids_sorted = sorted(sids)
        owner = entity_for_session.get(sids_sorted[0])
        results.append(
            CheckResult(
                code="worktree_paths_unique/collision",
                severity="error",
                file=getattr(owner, "rel_path", None),
                message=(
                    f"Worktree path {path!r} is claimed by multiple "
                    f"sessions: {', '.join(sids_sorted)}. Only one "
                    f"session may own a worktree directory."
                ),
                fix_hint=(
                    "Inspect each session's runtime_state.worktrees and "
                    "remove the stale entry, OR move one session's "
                    "worktree to a distinct path."
                ),
            )
        )

    return results
