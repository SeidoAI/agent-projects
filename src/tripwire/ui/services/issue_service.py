"""Issue read service — list, detail, validate.

Wraps :mod:`tripwire.core.store` to produce API-shaped models for the
``/api/projects/{pid}/issues`` routes. Mutation services (status updates,
generic patches) live in a later issue (KUI-24) — this module stays
read-only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tripwire.core.graph import cache as graph_cache
from tripwire.core.graph.refs import extract_references
from tripwire.core.node_store import node_exists
from tripwire.core.store import issue_exists, load_issue
from tripwire.core.store import list_issues as _core_list_issues
from tripwire.core.validator import ValidationReport, validate_project

logger = logging.getLogger("tripwire.ui.services.issue_service")

# Statuses that mean an upstream dependency is "clear" — an issue whose
# blockers are all in these states is NOT blocked.
_CLEAR_STATUSES: frozenset[str] = frozenset({"done", "ready", "updating"})

_EPIC_LABEL = "type/epic"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


ReferenceKind = Literal["node", "issue", "dangling"]


class Reference(BaseModel):
    """Resolved `[[ref]]` found in an issue body."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    ref: str
    resolves_as: ReferenceKind
    is_stale: bool


class IssueSummary(BaseModel):
    """Lightweight issue descriptor for list views."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    title: str
    status: str
    priority: str
    executor: str
    verifier: str
    kind: str | None = None
    agent: str | None = None
    labels: list[str] = Field(default_factory=list)
    parent: str | None = None
    repo: str | None = None
    blocked_by: list[str] = Field(default_factory=list)
    is_blocked: bool
    is_epic: bool
    created_at: str | None = None
    updated_at: str | None = None


class IssueDetail(IssueSummary):
    """Full issue detail — summary fields plus body and refs."""

    body: str = ""
    refs: list[Reference] = Field(default_factory=list)


class IssueFilters(BaseModel):
    """Optional filters passed to :func:`list_issues`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str | None = None
    executor: str | None = None
    label: str | None = None
    parent: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_epic(labels: list[str]) -> bool:
    return _EPIC_LABEL in labels


def _iso(value: object) -> str | None:
    """Render a datetime field as an ISO 8601 string, preserving raw str input.

    The core issue model uses `datetime | None`, but YAML round-tripping may
    leave naive strings behind; accept both to avoid raising at read time.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()  # type: ignore[no-any-return]


def _stale_node_set(project_dir: Path) -> set[str]:
    """Return the graph cache's stale_nodes list as a set.

    Returns an empty set when the cache is missing. We never build the
    cache from here — UI reads must never mutate project state.
    """
    cache = graph_cache.load_index(project_dir)
    if cache is None:
        return set()
    return set(cache.stale_nodes)


def _build_status_index(project_dir: Path) -> dict[str, str]:
    """Map every issue key → status for fast is_blocked derivation.

    Reads the graph cache's file set first so the common path is one cache
    lookup + N small disk reads (one per issue file). We still need to read
    the issue yaml for its `status` field because the cache fingerprint
    doesn't store it. A future optimisation: extend FileFingerprint with
    status if this shows up on a hot path.
    """
    index: dict[str, str] = {}
    for issue in _core_list_issues(project_dir):
        index[issue.id] = issue.status
    return index


def _derive_is_blocked(
    blocked_by: list[str],
    status_index: dict[str, str],
) -> bool:
    """An issue is blocked iff any blocker's status is NOT in _CLEAR_STATUSES.

    Unknown blockers (missing from the index) count as blocking — an
    unresolvable reference should not silently flip to "clear".
    """
    for blocker in blocked_by:
        status = status_index.get(blocker)
        if status is None or status not in _CLEAR_STATUSES:
            return True
    return False


def _resolve_reference(project_dir: Path, ref: str, stale_nodes: set[str]) -> Reference:
    """Classify a `[[ref]]` as node/issue/dangling and attach staleness."""
    if node_exists(project_dir, ref):
        return Reference(
            ref=ref,
            resolves_as="node",
            is_stale=ref in stale_nodes,
        )
    if issue_exists(project_dir, ref):
        return Reference(ref=ref, resolves_as="issue", is_stale=False)
    return Reference(ref=ref, resolves_as="dangling", is_stale=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_issues(
    project_dir: Path,
    filters: IssueFilters | None = None,
) -> list[IssueSummary]:
    """Return every issue as an :class:`IssueSummary`, narrowed by *filters*.

    Filter semantics:

    - ``status`` — exact match.
    - ``executor`` — exact match.
    - ``label`` — membership: keep issues whose ``labels`` contain this
      string.
    - ``parent`` — exact match on the ``parent`` field.

    ``is_blocked`` is derived per-issue from the live status of each
    ``blocked_by`` key, via a single in-memory index built once per call.
    """
    filters = filters or IssueFilters()
    raw_issues = _core_list_issues(project_dir)
    status_index = {i.id: i.status for i in raw_issues}

    out: list[IssueSummary] = []
    for issue in raw_issues:
        if filters.status is not None and issue.status != filters.status:
            continue
        if filters.executor is not None and issue.executor != filters.executor:
            continue
        if filters.label is not None and filters.label not in issue.labels:
            continue
        if filters.parent is not None and issue.parent != filters.parent:
            continue

        out.append(
            IssueSummary(
                id=issue.id,
                title=issue.title,
                status=issue.status,
                priority=issue.priority,
                executor=issue.executor,
                verifier=issue.verifier,
                kind=issue.kind,
                agent=issue.agent,
                labels=list(issue.labels),
                parent=issue.parent,
                repo=issue.repo,
                blocked_by=list(issue.blocked_by),
                is_blocked=_derive_is_blocked(issue.blocked_by, status_index),
                is_epic=_is_epic(issue.labels),
                created_at=_iso(issue.created_at),
                updated_at=_iso(issue.updated_at),
            )
        )
    return out


def get_issue(project_dir: Path, key: str) -> IssueDetail:
    """Return the full :class:`IssueDetail` for *key*.

    Raises :class:`FileNotFoundError` if the issue file is missing.
    """
    issue = load_issue(project_dir, key)

    status_index = _build_status_index(project_dir)
    stale_nodes = _stale_node_set(project_dir)

    # Preserve the order a reader sees them in, but dedupe — an issue that
    # mentions `[[user-model]]` three times should show one entry.
    seen: set[str] = set()
    refs: list[Reference] = []
    for raw in extract_references(issue.body):
        if raw in seen:
            continue
        seen.add(raw)
        refs.append(_resolve_reference(project_dir, raw, stale_nodes))

    return IssueDetail(
        id=issue.id,
        title=issue.title,
        status=issue.status,
        priority=issue.priority,
        executor=issue.executor,
        verifier=issue.verifier,
        kind=issue.kind,
        agent=issue.agent,
        labels=list(issue.labels),
        parent=issue.parent,
        repo=issue.repo,
        blocked_by=list(issue.blocked_by),
        is_blocked=_derive_is_blocked(issue.blocked_by, status_index),
        is_epic=_is_epic(issue.labels),
        body=issue.body,
        refs=refs,
        created_at=_iso(issue.created_at),
        updated_at=_iso(issue.updated_at),
    )


def validate_issue(project_dir: Path, key: str) -> ValidationReport:
    """Return a :class:`ValidationReport` scoped to findings touching *key*.

    The underlying ``validate_project`` does not yet accept a selector, so
    we run the full validation and filter findings whose ``file`` points at
    ``issues/<key>/`` — that's the set of checks the UI's issue page cares
    about. The report's summary counts, exit code, and durations are
    recomputed from the filtered findings.
    """
    report = validate_project(project_dir, strict=False, fix=False)
    prefix = f"issues/{key}/"

    def _matches(finding_file: str | None) -> bool:
        if finding_file is None:
            return False
        return finding_file.startswith(prefix)

    filtered_errors = [f for f in report.errors if _matches(f.file)]
    filtered_warnings = [f for f in report.warnings if _matches(f.file)]
    filtered_fixed = [f for f in report.fixed if _matches(f.file)]

    if filtered_errors:
        exit_code = 2
    elif filtered_warnings:
        exit_code = 1
    else:
        exit_code = 0

    return ValidationReport(
        version=report.version,
        exit_code=exit_code,
        errors=filtered_errors,
        warnings=filtered_warnings,
        fixed=filtered_fixed,
        cache_rebuilt=report.cache_rebuilt,
        duration_ms=report.duration_ms,
    )


__all__ = [
    "IssueDetail",
    "IssueFilters",
    "IssueSummary",
    "Reference",
    "get_issue",
    "list_issues",
    "validate_issue",
]
