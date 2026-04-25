"""Pure-function renderer for `tripwire pr-summary`.

Takes a structured :class:`PrSummary` dataclass and produces the markdown
PR-comment body. Sections with non-zero changes open by default; the rest
collapse so reviewers can scan the comment quickly. The first line is the
marker comment that ``peter-evans/create-or-update-comment`` matches on to
update one comment per PR rather than spamming a new one each push.

This module has no I/O — fixtures and tests can construct ``PrSummary``
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MARKER = "<!-- tripwire-pr-summary -->"
MAX_CHARS = 65_000  # GitHub PR comment cap
ID_LIST_CAP = 20


@dataclass
class ValidationSection:
    base_errors: int = 0
    head_errors: int = 0
    base_warnings: int = 0
    head_warnings: int = 0


@dataclass
class IssueStatusChange:
    id: str
    from_status: str
    to_status: str


@dataclass
class IssuesSection:
    base_counts: dict[str, int] = field(default_factory=dict)
    head_counts: dict[str, int] = field(default_factory=dict)
    changes: list[IssueStatusChange] = field(default_factory=list)


@dataclass
class SessionLifecycleChange:
    id: str
    from_status: str
    to_status: str


@dataclass
class SessionsSection:
    base_counts: dict[str, int] = field(default_factory=dict)
    head_counts: dict[str, int] = field(default_factory=dict)
    changes: list[SessionLifecycleChange] = field(default_factory=list)


@dataclass
class ConceptGraphSection:
    nodes_added: list[str] = field(default_factory=list)
    nodes_removed: list[str] = field(default_factory=list)
    nodes_promoted: list[str] = field(default_factory=list)
    base_orphan_refs: int = 0
    head_orphan_refs: int = 0
    base_stale_nodes: int = 0
    head_stale_nodes: int = 0


@dataclass
class CriticalPathSection:
    base_length: int = 0
    head_length: int = 0


@dataclass
class WorkspaceSyncSection:
    linked: bool = False
    base_promotion_candidates: int = 0
    head_promotion_candidates: int = 0
    base_workspace_origin_count: int = 0
    head_workspace_origin_count: int = 0


@dataclass
class LintSection:
    base_errors: int = 0
    head_errors: int = 0
    base_warnings: int = 0
    head_warnings: int = 0


@dataclass
class PrSummary:
    base_sha: str = ""
    head_sha: str = ""
    project_name: str = ""
    validation: ValidationSection = field(default_factory=ValidationSection)
    issues: IssuesSection = field(default_factory=IssuesSection)
    sessions: SessionsSection = field(default_factory=SessionsSection)
    concept_graph: ConceptGraphSection = field(default_factory=ConceptGraphSection)
    critical_path: CriticalPathSection = field(default_factory=CriticalPathSection)
    workspace_sync: WorkspaceSyncSection = field(default_factory=WorkspaceSyncSection)
    lint: LintSection = field(default_factory=LintSection)


# ============================================================================
# Render
# ============================================================================


def render(summary: PrSummary) -> str:
    """Render *summary* as the PR-comment markdown body."""
    parts: list[str] = [MARKER, "## Tripwire PR summary", ""]
    head_label = _short(summary.head_sha) or "HEAD"
    base_label = _short(summary.base_sha) or "base"
    header = f"`{base_label}` → `{head_label}`"
    if summary.project_name:
        header = f"**{summary.project_name}** · {header}"
    parts.append(header)
    parts.append("")

    parts.append(_render_validation(summary.validation))
    parts.append(_render_issues(summary.issues))
    parts.append(_render_sessions(summary.sessions))
    parts.append(_render_concept_graph(summary.concept_graph))
    parts.append(_render_critical_path(summary.critical_path))
    parts.append(_render_workspace_sync(summary.workspace_sync))
    parts.append(_render_lint(summary.lint))

    out = "\n\n".join(p for p in parts if p) + "\n"
    if len(out) > MAX_CHARS:
        budget = MAX_CHARS - len(_TRUNC_NOTE)
        out = out[:budget] + _TRUNC_NOTE
    return out


_TRUNC_NOTE = "\n\n_…(truncated at 65,000 chars)_\n"


def _short(sha: str) -> str:
    """Return the first 7 chars of *sha*, or "" if empty.

    Refs like ``origin/main`` (no hex) pass through unchanged.
    """
    if not sha:
        return ""
    if all(c in "0123456789abcdefABCDEF" for c in sha) and len(sha) > 7:
        return sha[:7]
    return sha


def _signed(n: int) -> str:
    """Render *n* as a signed delta (``+5``, ``-3``, ``0``)."""
    if n > 0:
        return f"+{n}"
    if n < 0:
        return str(n)
    return "0"


def _details(*, open_: bool, summary_line: str, body: str) -> str:
    attr = " open" if open_ else ""
    return f"<details{attr}>\n<summary>{summary_line}</summary>\n\n{body}\n\n</details>"


def _render_validation(v: ValidationSection) -> str:
    err_delta = v.head_errors - v.base_errors
    warn_delta = v.head_warnings - v.base_warnings
    is_open = v.head_errors > 0 or err_delta != 0 or warn_delta != 0

    if v.head_errors:
        icon = "✗"
    elif v.head_warnings:
        icon = "⚠"
    else:
        icon = "✓"

    summary_line = (
        f"{icon} Validation — {v.head_errors} error(s), "
        f"{v.head_warnings} warning(s) at HEAD"
    )
    if err_delta != 0 or warn_delta != 0:
        summary_line += f" (Δ {_signed(err_delta)}E / {_signed(warn_delta)}W)"

    body = (
        "| | base | head | Δ |\n"
        "|---|---|---|---|\n"
        f"| errors | {v.base_errors} | {v.head_errors} | {_signed(err_delta)} |\n"
        f"| warnings | {v.base_warnings} | {v.head_warnings} | {_signed(warn_delta)} |"
    )
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_issues(i: IssuesSection) -> str:
    is_open = bool(i.changes)
    moved = len(i.changes)
    summary_line = f"{'⚠' if moved else '✓'} Issues — {moved} status change(s)"

    body_parts: list[str] = []
    counts_table = _counts_table(i.base_counts, i.head_counts, axis_label="status")
    if counts_table:
        body_parts.append(counts_table)

    if i.changes:
        capped = i.changes[:ID_LIST_CAP]
        lines = [f"- `{c.id}`: {c.from_status} → {c.to_status}" for c in capped]
        if len(i.changes) > ID_LIST_CAP:
            lines.append(f"- _…+{len(i.changes) - ID_LIST_CAP} more_")
        body_parts.append("**Changes:**\n" + "\n".join(lines))
    else:
        body_parts.append("_No status changes._")

    body = "\n\n".join(body_parts)
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_sessions(s: SessionsSection) -> str:
    is_open = bool(s.changes)
    moved = len(s.changes)
    summary_line = f"{'⚠' if moved else '✓'} Sessions — {moved} status change(s)"

    body_parts: list[str] = []
    counts_table = _counts_table(s.base_counts, s.head_counts, axis_label="status")
    if counts_table:
        body_parts.append(counts_table)

    if s.changes:
        capped = s.changes[:ID_LIST_CAP]
        lines = [f"- `{c.id}`: {c.from_status} → {c.to_status}" for c in capped]
        if len(s.changes) > ID_LIST_CAP:
            lines.append(f"- _…+{len(s.changes) - ID_LIST_CAP} more_")
        body_parts.append("**Changes:**\n" + "\n".join(lines))
    else:
        body_parts.append("_No state changes._")

    body = "\n\n".join(body_parts)
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_concept_graph(g: ConceptGraphSection) -> str:
    orphan_delta = g.head_orphan_refs - g.base_orphan_refs
    stale_delta = g.head_stale_nodes - g.base_stale_nodes
    has_changes = bool(
        g.nodes_added
        or g.nodes_removed
        or g.nodes_promoted
        or orphan_delta
        or stale_delta
    )
    is_open = has_changes

    summary_line = (
        f"{'⚠' if has_changes else '✓'} Concept graph — "
        f"+{len(g.nodes_added)} / -{len(g.nodes_removed)} / "
        f"↑{len(g.nodes_promoted)} promoted"
    )

    body_parts: list[str] = []
    if g.nodes_added:
        body_parts.append(_id_list("Added", g.nodes_added))
    if g.nodes_removed:
        body_parts.append(_id_list("Removed", g.nodes_removed))
    if g.nodes_promoted:
        body_parts.append(_id_list("Promoted to workspace", g.nodes_promoted))

    counts_table = (
        "| | base | head | Δ |\n"
        "|---|---|---|---|\n"
        f"| orphan refs | {g.base_orphan_refs} | {g.head_orphan_refs} | "
        f"{_signed(orphan_delta)} |\n"
        f"| stale nodes | {g.base_stale_nodes} | {g.head_stale_nodes} | "
        f"{_signed(stale_delta)} |"
    )
    body_parts.append(counts_table)

    body = "\n\n".join(body_parts)
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_critical_path(cp: CriticalPathSection) -> str:
    delta = cp.head_length - cp.base_length
    is_open = delta != 0

    if delta < 0:
        verb = f"shortened by {-delta}"
        icon = "✓"
    elif delta > 0:
        verb = f"lengthened by {delta}"
        icon = "⚠"
    else:
        verb = "unchanged"
        icon = "✓"

    summary_line = (
        f"{icon} Critical path — {verb} (base {cp.base_length} → head {cp.head_length})"
    )
    body = (
        "| | base | head | Δ |\n"
        "|---|---|---|---|\n"
        f"| length | {cp.base_length} | {cp.head_length} | {_signed(delta)} |"
    )
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_workspace_sync(w: WorkspaceSyncSection) -> str:
    if not w.linked:
        return _details(
            open_=False,
            summary_line="✓ Workspace sync — project not linked",
            body="_This project is not linked to a workspace._",
        )
    promo_delta = w.head_promotion_candidates - w.base_promotion_candidates
    is_open = w.head_promotion_candidates > 0 or promo_delta != 0

    summary_line = (
        f"{'⚠' if w.head_promotion_candidates else '✓'} Workspace sync — "
        f"{w.head_promotion_candidates} promotion candidate(s)"
    )
    body = (
        "| | base | head | Δ |\n"
        "|---|---|---|---|\n"
        f"| workspace-origin nodes | {w.base_workspace_origin_count} | "
        f"{w.head_workspace_origin_count} | "
        f"{_signed(w.head_workspace_origin_count - w.base_workspace_origin_count)} |\n"
        f"| promotion candidates | {w.base_promotion_candidates} | "
        f"{w.head_promotion_candidates} | {_signed(promo_delta)} |"
    )
    return _details(open_=is_open, summary_line=summary_line, body=body)


def _render_lint(li: LintSection) -> str:
    err_delta = li.head_errors - li.base_errors
    warn_delta = li.head_warnings - li.base_warnings
    has_findings = li.head_errors > 0 or li.head_warnings > 0
    is_open = has_findings or err_delta != 0 or warn_delta != 0

    if li.head_errors:
        icon = "✗"
    elif li.head_warnings:
        icon = "⚠"
    else:
        icon = "✓"

    summary_line = (
        f"{icon} Lint — {li.head_errors} error(s), {li.head_warnings} warning(s)"
    )
    body = (
        "| | base | head | Δ |\n"
        "|---|---|---|---|\n"
        f"| errors | {li.base_errors} | {li.head_errors} | {_signed(err_delta)} |\n"
        f"| warnings | {li.base_warnings} | {li.head_warnings} | "
        f"{_signed(warn_delta)} |"
    )
    return _details(open_=is_open, summary_line=summary_line, body=body)


# ============================================================================
# Helpers
# ============================================================================


def _counts_table(
    base: dict[str, int], head: dict[str, int], *, axis_label: str
) -> str:
    """Render a base/head/Δ count table for a categorical axis.

    Returns an empty string if both sides are empty (so callers can skip
    rendering an empty table).
    """
    keys = sorted(set(base) | set(head))
    if not keys:
        return ""
    rows = [f"| {axis_label} | base | head | Δ |", "|---|---|---|---|"]
    for k in keys:
        b = base.get(k, 0)
        h = head.get(k, 0)
        rows.append(f"| {k} | {b} | {h} | {_signed(h - b)} |")
    return "\n".join(rows)


def _id_list(title: str, ids: list[str]) -> str:
    capped = ids[:ID_LIST_CAP]
    bullet_lines = [f"- `{i}`" for i in capped]
    if len(ids) > ID_LIST_CAP:
        bullet_lines.append(f"- _…+{len(ids) - ID_LIST_CAP} more_")
    return f"**{title} ({len(ids)}):**\n" + "\n".join(bullet_lines)
