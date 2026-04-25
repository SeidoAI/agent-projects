"""Pure README renderer.

Composes existing tripwire primitives (issues, sessions, project config)
into a structured context dict, then runs the configured Jinja template
against it. No external commands, no network — the workflow / CLI layer
is responsible for any "fetch recent merges" enrichment that wants to
shell out to `gh`.

`build_render_context` is split out from `render` so callers that only
want the structured data (e.g. a future JSON output mode) don't pay the
template-render cost.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tripwire import __version__ as _tripwire_version
from tripwire.core.dependency_graph import build_dependency_graph
from tripwire.core.session_agenda import build_agenda
from tripwire.core.session_mermaid import render_session_mermaid
from tripwire.core.session_store import list_sessions
from tripwire.core.store import list_issues, load_project
from tripwire.templates import get_templates_dir

# Issue statuses that count as "closed" for the at-a-glance summary.
# `done` and `canceled` are the explicit terminal states in the default
# transitions; `verified` is debatable but most projects treat verified
# as "closed enough".
_CLOSED_ISSUE_STATUSES: frozenset[str] = frozenset({"done", "canceled"})

# Default template lives under packaged templates.
DEFAULT_TEMPLATE_RELPATH = "readme/default.md.j2"

# Marker that identifies a generated README. The first line of every
# rendered file carries this so future tooling can detect generated
# files (e.g. drift detection in `tripwire migrate`).
README_MARKER = "<!-- tripwire-readme-auto -->"


# ============================================================================
# Public API
# ============================================================================


def render(
    project_dir: Path,
    *,
    template_path: Path | None = None,
    now: datetime | None = None,
    recent_merges: list[str] | None = None,
) -> str:
    """Render the project README to a string.

    Args:
        project_dir: Path to the project root (contains `project.yaml`).
        template_path: Optional override for the default template. Resolved
            in this order: explicit arg → `<project>/.tripwire/readme.md.j2`
            → packaged default.
        now: Override for the regeneration timestamp. Defaults to UTC
            current time. Override in tests for stable snapshots.
        recent_merges: Optional list of one-line merge summaries to inject
            into the "Recent merges" section. Workflow is responsible for
            fetching these (e.g. via `gh pr list --state merged`).

    Returns:
        The fully-rendered markdown. The first line is `README_MARKER`.
    """
    ctx = build_render_context(project_dir, now=now, recent_merges=recent_merges)
    template_file = _resolve_template(project_dir, template_path)
    return _render_with_template(template_file, ctx)


def build_render_context(
    project_dir: Path,
    *,
    now: datetime | None = None,
    recent_merges: list[str] | None = None,
) -> dict[str, Any]:
    """Build the dict passed to the Jinja template.

    Pure function — no template render. A future JSON output mode could
    serialise this directly.
    """
    project = load_project(project_dir)
    sessions = list_sessions(project_dir)
    issues = list_issues(project_dir)

    session_dicts = [
        {
            "id": s.id,
            "status": s.status,
            "blocked_by_sessions": list(s.blocked_by_sessions),
        }
        for s in sessions
    ]
    agenda = build_agenda(session_dicts)

    issue_status_counts: dict[str, int] = {}
    for issue in issues:
        issue_status_counts[issue.status] = issue_status_counts.get(issue.status, 0) + 1
    issue_open = sum(
        c for st, c in issue_status_counts.items() if st not in _CLOSED_ISSUE_STATUSES
    )
    issue_closed = sum(
        c for st, c in issue_status_counts.items() if st in _CLOSED_ISSUE_STATUSES
    )

    # Issue critical path is independent of session critical path. Both
    # are useful, but the README's "critical path" line is for sessions —
    # they're the unit of work the reader cares about.
    issue_dep = build_dependency_graph(issues)

    workspace_path = (
        project.workspace.path if project.workspace and project.workspace.path else None
    )

    health = _health_badge(agenda)
    session_summary = (
        f"{len(agenda.in_flight)} in flight · "
        f"{len(agenda.completed_sessions)} done · "
        f"{len(agenda.launchable)} ready"
    )
    issue_summary = f"{issue_open} open · {issue_closed} closed"

    regenerated_at = (now or datetime.now(tz=timezone.utc)).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    active_sessions = [
        {
            "id": info.id,
            "status": info.status,
            "issues": _issues_for_session(sessions, info.id),
        }
        for info in sorted(agenda.in_flight, key=lambda i: i.id)
    ]

    all_sessions = [
        {"id": s.id, "status": s.status} for s in sorted(sessions, key=lambda s: s.id)
    ]

    issues_by_status = [
        {"status": st, "count": cnt} for st, cnt in sorted(issue_status_counts.items())
    ]

    launchable = [
        {"session_id": r.session_id, "rationale": r.rationale}
        for r in agenda.recommendations[:3]
    ]

    links = _build_links(project, workspace_path)

    return {
        "project_name": project.name,
        "project_description": project.description,
        "tripwire_version": project.tripwire_version or _tripwire_version,
        "health_badge": health,
        "session_summary": session_summary,
        "issue_summary": issue_summary,
        "regenerated_at": regenerated_at,
        "validation_label": _validation_label(agenda),
        "session_in_flight": len(agenda.in_flight),
        "session_done": len(agenda.completed_sessions),
        "issue_open": issue_open,
        "issue_closed": issue_closed,
        "critical_path_len": len(agenda.critical_path),
        "session_mermaid": render_session_mermaid(sessions),
        "active_sessions": active_sessions,
        "recent_merges": list(recent_merges or []),
        "critical_path": list(agenda.critical_path),
        "issue_critical_path": list(issue_dep.critical_path),
        "launchable": launchable,
        "workspace_path": workspace_path,
        "total_issues": len(issues),
        "issues_by_status": issues_by_status,
        "total_sessions": len(sessions),
        "all_sessions": all_sessions,
        "links": links,
    }


# ============================================================================
# Internals
# ============================================================================


def _resolve_template(project_dir: Path, override: Path | None) -> Path:
    """Pick the template file. Order: explicit override → project override
    at `.tripwire/readme.md.j2` → packaged default."""
    if override is not None:
        if not override.is_file():
            raise FileNotFoundError(f"Template not found: {override}")
        return override.resolve()

    project_override = project_dir / ".tripwire" / "readme.md.j2"
    if project_override.is_file():
        return project_override.resolve()

    packaged = get_templates_dir() / DEFAULT_TEMPLATE_RELPATH
    if not packaged.is_file():
        raise FileNotFoundError(
            f"Packaged default template missing: {packaged}. "
            "This is a package installation problem."
        )
    return packaged


def _render_with_template(template_path: Path, ctx: dict[str, Any]) -> str:
    """Render a Jinja template file with the given context.

    Uses `StrictUndefined` so a typo in a template variable is a render
    error, not a silent empty string in the output.
    """
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    template = env.get_template(template_path.name)
    return template.render(**ctx)


def _health_badge(agenda) -> str:
    """A short emoji + label summarising overall project health."""
    if not agenda.totals:
        return "🟢 Empty"
    if agenda.all_completed:
        return "✓ All done"
    if agenda.in_flight:
        return "🚧 In progress"
    if agenda.launchable:
        return "🟡 Ready"
    return "🔵 Planned"


def _validation_label(agenda) -> str:
    """A short text label for the at-a-glance "Validation" cell.

    The renderer doesn't run `tripwire validate` directly (would couple
    rendering to validation), so we report a structural heuristic: any
    warnings on the agenda → `⚠ N warnings`; cycles would have crashed
    `build_agenda`, so reaching this point means no cycles.
    """
    if agenda.warnings:
        return f"⚠ {len(agenda.warnings)} warning{'s' if len(agenda.warnings) != 1 else ''}"
    return "✓ structure ok"


def _issues_for_session(sessions: list, sid: str) -> list[str]:
    """Return the issues field for a given session id (empty if missing)."""
    for s in sessions:
        if s.id == sid:
            return list(s.issues)
    return []


def _build_links(project, workspace_path: str | None) -> list[dict[str, str]]:
    """Build the Links section entries from project repos + workspace pointer."""
    links: list[dict[str, str]] = []
    for slug in sorted(project.repos.keys()):
        links.append({"label": slug, "target": f"https://github.com/{slug}"})
    if workspace_path:
        links.append({"label": "workspace", "target": workspace_path})
    return links
