"""Compute the :class:`PrSummary` delta between two git SHAs.

The strategy is straightforward: ``git worktree add --detach`` each SHA
into a temp directory, gather a :class:`_StateSnapshot` from project
state at that SHA via the existing core read-only functions, then build
a :class:`PrSummary` from the two snapshots.

Worktree-based checkout (rather than mutating HEAD) keeps the caller's
working tree untouched, which matters in CI where the head SHA *is* the
working tree.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.core.pr_summary_renderer import (
    ConceptGraphSection,
    CriticalPathSection,
    IssuesSection,
    IssueStatusChange,
    LintSection,
    PrSummary,
    SessionLifecycleChange,
    SessionsSection,
    ValidationSection,
    WorkspaceSyncSection,
)

# ============================================================================
# Snapshot
# ============================================================================


@dataclass
class _NodeFacts:
    scope: str
    origin: str


@dataclass
class _StateSnapshot:
    """Read-only project state captured at one git SHA.

    Fields are kept primitive (counts, dicts of ids → status, etc.) so
    delta computation is straightforward dict arithmetic.
    """

    project_name: str = ""
    project_exists: bool = False
    issue_status_by_id: dict[str, str] = field(default_factory=dict)
    session_status_by_id: dict[str, str] = field(default_factory=dict)
    nodes_by_id: dict[str, _NodeFacts] = field(default_factory=dict)
    validate_errors: int = 0
    validate_warnings: int = 0
    stale_node_count: int = 0
    orphan_ref_count: int = 0
    critical_path_length: int = 0
    lint_errors: int = 0
    lint_warnings: int = 0
    workspace_linked: bool = False
    workspace_promotion_candidates: int = 0
    workspace_origin_count: int = 0


# ============================================================================
# Public entry point
# ============================================================================


def compute_pr_summary(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    project_dir: str = "",
) -> PrSummary:
    """Build a :class:`PrSummary` for the diff range *base_sha*..*head_sha*.

    *repo* is the git repository root. *project_dir* is the relative
    path from the repo root to the tripwire project (default empty —
    project lives at the repo root, which is the common case).

    Both SHAs must resolve to commits in *repo*; pass any ref form git
    accepts (full sha, short sha, ``origin/main``, ``HEAD``, …).
    """
    base_state = _gather_at_sha(repo, base_sha, project_dir)
    head_state = _gather_at_sha(repo, head_sha, project_dir)
    return _build_summary(base_state, head_state, base_sha, head_sha)


# ============================================================================
# Snapshot gathering
# ============================================================================


def _gather_at_sha(repo: Path, sha: str, project_dir: str) -> _StateSnapshot:
    """Materialize *sha* in a temp worktree and read project state from it."""
    with _temp_worktree(repo, sha) as wt:
        target = wt / project_dir if project_dir else wt
        return _read_state(target)


@contextlib.contextmanager
def _temp_worktree(repo: Path, sha: str) -> Iterator[Path]:
    """Create a detached worktree at *sha* and yield its path; clean up on exit.

    ``git worktree add`` requires the leaf directory to not exist, so we
    create a parent tmpdir and point git at ``<parent>/wt`` inside it.
    """
    tmp_parent = Path(tempfile.mkdtemp(prefix="tripwire-pr-summary-"))
    wt = tmp_parent / "wt"
    try:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), sha],
            check=True,
            capture_output=True,
            text=True,
        )
        yield wt
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
            check=False,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(tmp_parent, ignore_errors=True)


def _read_state(project_dir: Path) -> _StateSnapshot:
    """Read project state from *project_dir* without mutating it.

    If the directory has no ``project.yaml`` (e.g. *sha* predates the
    project), return an empty snapshot rather than raising — the base
    side of a brand-new project should compare against "nothing".
    """
    from tripwire.core.graph.dependency import build_dependency_graph
    from tripwire.core.linter import Linter
    from tripwire.core.node_store import list_nodes
    from tripwire.core.session_store import list_sessions
    from tripwire.core.store import (
        ProjectNotFoundError,
        list_issues,
        load_project,
    )
    from tripwire.core.validator import validate_project

    try:
        project = load_project(project_dir)
    except (ProjectNotFoundError, ValueError):
        return _StateSnapshot()
    except FileNotFoundError:
        return _StateSnapshot()

    state = _StateSnapshot(project_name=project.name, project_exists=True)

    issues = list_issues(project_dir)
    state.issue_status_by_id = {i.id: i.status for i in issues}

    sessions = list_sessions(project_dir)
    state.session_status_by_id = {s.id: s.status for s in sessions}

    nodes = list_nodes(project_dir)
    state.nodes_by_id = {
        n.id: _NodeFacts(scope=n.scope, origin=n.origin) for n in nodes
    }

    # Validation report. We re-run validate (rather than reading the
    # cached report) so the snapshot reflects the SHA's actual state,
    # not a stale cache from an earlier run in a different worktree.
    report = validate_project(project_dir, strict=True, fix=False)
    state.validate_errors = len(report.errors)
    state.validate_warnings = len(report.warnings)
    state.orphan_ref_count = sum(
        1 for f in (*report.errors, *report.warnings) if f.code.startswith("ref/")
    )

    # Critical path comes from the dependency graph over current issues.
    state.critical_path_length = len(build_dependency_graph(issues).critical_path)

    # Stale-node count comes from the graph cache when present; if the
    # cache hasn't been built at this SHA, fall back to 0 — validate
    # rebuilds the cache, so by this point it should exist.
    from tripwire.core.graph import cache as graph_cache

    cache = graph_cache.load_index(project_dir)
    state.stale_node_count = len(cache.stale_nodes) if cache is not None else 0

    # Scoping lint — the only stage cheap enough to run per snapshot.
    findings = list(Linter(project_dir=project_dir).run_stage("scoping"))
    state.lint_errors = sum(1 for f in findings if f.severity == "error")
    state.lint_warnings = sum(1 for f in findings if f.severity == "warning")

    # Workspace state. Only populated when the project is linked.
    if project.workspace is not None:
        state.workspace_linked = True
        state.workspace_origin_count = sum(1 for n in nodes if n.origin == "workspace")
        state.workspace_promotion_candidates = sum(
            1 for n in nodes if n.origin == "local" and n.scope == "workspace"
        )

    return state


# ============================================================================
# Snapshot → PrSummary
# ============================================================================


def _build_summary(
    base: _StateSnapshot,
    head: _StateSnapshot,
    base_sha: str,
    head_sha: str,
) -> PrSummary:
    return PrSummary(
        base_sha=base_sha,
        head_sha=head_sha,
        project_name=head.project_name or base.project_name,
        validation=ValidationSection(
            base_errors=base.validate_errors,
            head_errors=head.validate_errors,
            base_warnings=base.validate_warnings,
            head_warnings=head.validate_warnings,
        ),
        issues=_issues_section(base, head),
        sessions=_sessions_section(base, head),
        concept_graph=_concept_graph_section(base, head),
        critical_path=CriticalPathSection(
            base_length=base.critical_path_length,
            head_length=head.critical_path_length,
        ),
        workspace_sync=_workspace_section(base, head),
        lint=LintSection(
            base_errors=base.lint_errors,
            head_errors=head.lint_errors,
            base_warnings=base.lint_warnings,
            head_warnings=head.lint_warnings,
        ),
    )


def _issues_section(base: _StateSnapshot, head: _StateSnapshot) -> IssuesSection:
    base_counts = dict(Counter(base.issue_status_by_id.values()))
    head_counts = dict(Counter(head.issue_status_by_id.values()))
    changes: list[IssueStatusChange] = []
    for issue_id in sorted(
        base.issue_status_by_id.keys() | head.issue_status_by_id.keys()
    ):
        b = base.issue_status_by_id.get(issue_id)
        h = head.issue_status_by_id.get(issue_id)
        if b is None and h is not None:
            changes.append(IssueStatusChange(issue_id, "—", h))
        elif h is None and b is not None:
            changes.append(IssueStatusChange(issue_id, b, "—"))
        elif b != h and b is not None and h is not None:
            changes.append(IssueStatusChange(issue_id, b, h))
    return IssuesSection(
        base_counts=base_counts, head_counts=head_counts, changes=changes
    )


def _sessions_section(base: _StateSnapshot, head: _StateSnapshot) -> SessionsSection:
    base_counts = dict(Counter(base.session_status_by_id.values()))
    head_counts = dict(Counter(head.session_status_by_id.values()))
    changes: list[SessionLifecycleChange] = []
    for sid in sorted(
        base.session_status_by_id.keys() | head.session_status_by_id.keys()
    ):
        b = base.session_status_by_id.get(sid)
        h = head.session_status_by_id.get(sid)
        if b is None and h is not None:
            changes.append(SessionLifecycleChange(sid, "—", h))
        elif h is None and b is not None:
            changes.append(SessionLifecycleChange(sid, b, "—"))
        elif b != h and b is not None and h is not None:
            changes.append(SessionLifecycleChange(sid, b, h))
    return SessionsSection(
        base_counts=base_counts, head_counts=head_counts, changes=changes
    )


def _concept_graph_section(
    base: _StateSnapshot, head: _StateSnapshot
) -> ConceptGraphSection:
    added = sorted(set(head.nodes_by_id) - set(base.nodes_by_id))
    removed = sorted(set(base.nodes_by_id) - set(head.nodes_by_id))
    promoted = sorted(
        nid
        for nid, h in head.nodes_by_id.items()
        if (b := base.nodes_by_id.get(nid)) is not None
        and b.origin == "local"
        and h.origin == "workspace"
    )
    return ConceptGraphSection(
        nodes_added=added,
        nodes_removed=removed,
        nodes_promoted=promoted,
        base_orphan_refs=base.orphan_ref_count,
        head_orphan_refs=head.orphan_ref_count,
        base_stale_nodes=base.stale_node_count,
        head_stale_nodes=head.stale_node_count,
    )


def _workspace_section(
    base: _StateSnapshot, head: _StateSnapshot
) -> WorkspaceSyncSection:
    return WorkspaceSyncSection(
        linked=head.workspace_linked or base.workspace_linked,
        base_promotion_candidates=base.workspace_promotion_candidates,
        head_promotion_candidates=head.workspace_promotion_candidates,
        base_workspace_origin_count=base.workspace_origin_count,
        head_workspace_origin_count=head.workspace_origin_count,
    )
