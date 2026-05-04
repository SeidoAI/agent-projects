"""`tripwire validate` — run the validation gate against a project.

Thin CLI wrapper over `core.validator.validate_project`. Exits with the
report's exit code so shell pipelines and orchestrators can branch on the
result:

- 0 → clean
- 1 → warnings only
- 2 → one or more errors

Output formats:
- `text` (default): human-readable rendering with rich styling
- `json`: the full report serialised to the spec's JSON schema
- `summary`: error-code counts (compact, for progress monitoring)
- `compact`: one line per error (for fix-by-fix work)
- `--count`: just the error count as an integer
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from tripwire.cli._profiling import profileable
from tripwire.core.validator import (
    CheckResult,
    ValidationReport,
    validate_project,
)

console = Console()


@click.command(name="validate")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "summary", "compact"]),
    default="text",
    show_default=True,
    help="Output format: text (human-readable), json (structured), summary (code counts), compact (one line per error).",
)
@click.option(
    "--count",
    "count_only",
    is_flag=True,
    help="Print only the error count (integer) and exit.",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Auto-fix the defined subset of issues (timestamps, UUIDs, etc.).",
)
@click.option(
    "--select",
    "select_expr",
    default=None,
    help="Selector: ID+ (downstream), +ID (upstream), ID+N (N hops), tag:NAME.",
)
@profileable
def validate_cmd(
    project_dir: Path,
    output_format: str,
    count_only: bool,
    fix: bool,
    select_expr: str | None,
) -> None:
    """Run the validation gate.

    The gate the agent runs after every batch of file writes. Always
    rebuilds `graph/index.yaml` as a side effect. Strict-by-default:
    warnings are errors. Run with ``--fix`` to auto-repair trivial
    issues. (``--strict`` was hard-removed in stage 1 of the workflow
    codification — heuristic-as-tripwire promotion ships in stage 2 as
    ``--heuristics-as-tripwires``.)
    """
    resolved = project_dir.expanduser().resolve()
    report = validate_project(resolved, strict=True, fix=fix)

    if select_expr:
        _filter_report_by_selector(report, resolved, select_expr)

    if count_only:
        click.echo(len(report.errors))
    elif output_format == "json":
        click.echo(json.dumps(report.to_json(), indent=2))
    elif output_format == "summary":
        click.echo(report.to_summary())
    elif output_format == "compact":
        click.echo(report.to_compact())
    else:
        _render_text(report)

    sys.exit(report.exit_code)


def _filter_report_by_selector(
    report: ValidationReport, project_dir: Path, select_expr: str
) -> None:
    """Filter a validation report in-place to only findings matching
    the selector's entity set."""
    from tripwire.core.selectors import resolve_selector

    try:
        result = resolve_selector(select_expr, project_dir)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    selected_ids = result.ids

    def _matches(finding: CheckResult) -> bool:
        """True if the finding relates to a selected entity."""
        if not finding.file:
            return True  # project-level findings always included
        # Extract entity ID from file path:
        #   issues/SEI-1/issue.yaml → SEI-1 (parent dir name)
        #   nodes/user-model.yaml → user-model (stem)
        #   sessions/api-endpoints/session.yaml → api-endpoints (parent dir name)
        p = Path(finding.file)
        if p.name in {"issue.yaml", "session.yaml"}:
            return p.parent.name in selected_ids
        return p.stem in selected_ids

    report.errors = [f for f in report.errors if _matches(f)]
    report.warnings = [f for f in report.warnings if _matches(f)]
    report.fixed = [f for f in report.fixed if _matches(f)]
    # Recompute exit code
    if report.errors:
        report.exit_code = 2
    elif report.warnings:
        report.exit_code = 1
    else:
        report.exit_code = 0


def _group_by_category(
    findings: list[CheckResult],
) -> dict[str, list[CheckResult]]:
    """Group findings by the category prefix (the part before ``/``)."""
    groups: dict[str, list[CheckResult]] = {}
    for f in findings:
        cat = f.code.split("/")[0] if "/" in f.code else f.code
        groups.setdefault(cat, []).append(f)
    return dict(sorted(groups.items()))


def _render_text(report: ValidationReport) -> None:
    """Render the validation report as styled text via rich."""
    # Header line
    if report.exit_code == 0:
        console.print("[bold green]validate passed[/bold green]")
    elif report.exit_code == 1:
        console.print(
            f"[bold yellow]validate: {len(report.warnings)} warning(s)[/bold yellow]"
        )
    else:
        console.print(
            f"[bold red]validate: {len(report.errors)} error(s), "
            f"{len(report.warnings)} warning(s)[/bold red]"
        )

    # Summary line
    console.print(
        f"  [dim]duration: {report.duration_ms}ms  "
        f"cache rebuilt: {str(report.cache_rebuilt).lower()}[/dim]"
    )

    # Category summary
    cats = report.category_summary
    if cats:
        parts = [
            f"{cat}: {c['errors']}E/{c['warnings']}W"
            for cat, c in sorted(cats.items())
            if c["errors"] or c["warnings"]
        ]
        if parts:
            console.print(f"  [dim]categories: {', '.join(parts)}[/dim]")

    if report.fixed:
        console.print(f"\n[bold cyan]Fixed ({len(report.fixed)}):[/bold cyan]")
        for cat, items in _group_by_category(report.fixed).items():
            console.print(f"  [bold cyan]\\[{cat}][/bold cyan] ({len(items)})")
            for fix in items:
                _render_finding(fix, severity_color="cyan")

    if report.errors:
        console.print(f"\n[bold red]Errors ({len(report.errors)}):[/bold red]")
        for cat, items in _group_by_category(report.errors).items():
            console.print(f"  [bold red]\\[{cat}][/bold red] ({len(items)})")
            for err in items:
                _render_finding(err, severity_color="red")

    if report.warnings:
        console.print(
            f"\n[bold yellow]Warnings ({len(report.warnings)}):[/bold yellow]"
        )
        for cat, items in _group_by_category(report.warnings).items():
            console.print(f"  [bold yellow]\\[{cat}][/bold yellow] ({len(items)})")
            for warn in items:
                _render_finding(warn, severity_color="yellow")


def _render_finding(finding: CheckResult, severity_color: str) -> None:
    """Render one CheckResult as two to three lines of styled text."""
    location = finding.file or ""
    if finding.field:
        location = f"{location}:{finding.field}" if location else finding.field
    if finding.line is not None:
        location = f"{location}:{finding.line}"

    header = f"  [{severity_color}]{finding.code}[/{severity_color}]"
    if location:
        header = f"{header}  [dim]{location}[/dim]"
    console.print(header)
    console.print(f"    {finding.message}")
    if finding.fix_hint:
        console.print(f"    [dim]hint: {finding.fix_hint}[/dim]")
