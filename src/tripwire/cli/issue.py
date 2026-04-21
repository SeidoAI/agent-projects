"""`tripwire issue` — per-issue operations (artifact, insights).

v0.7b introduces per-issue artifacts (developer.md, verified.md) alongside
the issue YAML. This module exposes the read/render/verify helpers; the
PM slash command `/pm-issue-artifact` drives it.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.core import paths
from tripwire.core.issue_artifact_store import (
    load_issue_artifact_manifest,
    status_at_or_past,
)
from tripwire.core.store import load_issue

console = Console()


@click.group(name="issue")
def issue_cmd() -> None:
    """Per-issue operations (artifact + insights subgroups)."""


@issue_cmd.group(name="artifact")
def issue_artifact_cmd() -> None:
    """Issue artifact operations (developer.md, verified.md)."""


@issue_artifact_cmd.command("list")
@click.argument("issue_key")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def issue_artifact_list_cmd(
    issue_key: str, project_dir: Path, output_format: str
) -> None:
    """List expected artifacts for an issue and their presence state."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    manifest = load_issue_artifact_manifest(resolved)

    rows: list[dict] = []
    for entry in manifest.artifacts:
        file_path = paths.issue_dir(resolved, issue_key) / entry.file
        rows.append(
            {
                "name": entry.name,
                "file": entry.file,
                "required": entry.required,
                "required_at_status": entry.required_at_status,
                "produced_by": entry.produced_by,
                "present": file_path.is_file(),
                "issue_status": issue.status,
            }
        )

    if output_format == "json":
        click.echo(json.dumps(rows, indent=2))
        return

    table = Table(title=f"Issue {issue_key} artifacts")
    table.add_column("name")
    table.add_column("file")
    table.add_column("required_at")
    table.add_column("produced_by")
    table.add_column("state")
    for row in rows:
        state = "✓ present" if row["present"] else "MISSING"
        table.add_row(
            row["name"],
            row["file"],
            row["required_at_status"],
            row["produced_by"],
            state,
        )
    console.print(table)


@issue_artifact_cmd.command("init")
@click.argument("issue_key")
@click.argument("artifact_name")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing artifact",
)
@click.option(
    "--produced-by",
    default=None,
    help="Override the produced_by attribution (defaults to manifest)",
)
def issue_artifact_init_cmd(
    issue_key: str,
    artifact_name: str,
    project_dir: Path,
    force: bool,
    produced_by: str | None,
) -> None:
    """Render the artifact template into the issue directory."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    manifest = load_issue_artifact_manifest(resolved)
    entry = next((e for e in manifest.artifacts if e.name == artifact_name), None)
    if entry is None:
        available = ", ".join(e.name for e in manifest.artifacts)
        raise click.ClickException(
            f"Unknown artifact {artifact_name!r}. Available: {available}"
        )

    target = paths.issue_dir(resolved, issue_key) / entry.file
    if target.is_file() and not force:
        raise click.ClickException(
            f"{target} already exists. Use --force to overwrite."
        )

    import tripwire

    template_root = Path(tripwire.__file__).parent / "templates" / "issue_artifacts"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    template = env.get_template(entry.template)
    rendered = template.render(
        issue=issue,
        project_dir=resolved,
        produced_by=produced_by or entry.produced_by,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    click.echo(f"Wrote {target.relative_to(resolved)}")


@issue_artifact_cmd.command("verify")
@click.argument("issue_key")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def issue_artifact_verify_cmd(issue_key: str, project_dir: Path) -> None:
    """Exit-1 if any required artifact for this issue is missing."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    manifest = load_issue_artifact_manifest(resolved)

    missing: list[str] = []
    for entry in manifest.artifacts:
        if not entry.required:
            continue
        if not status_at_or_past(issue.status, entry.required_at_status, resolved):
            continue
        file_path = paths.issue_dir(resolved, issue_key) / entry.file
        if not file_path.is_file():
            missing.append(entry.file)

    if missing:
        for f in missing:
            click.echo(f"MISSING: {f}")
        raise click.exceptions.Exit(1)
    click.echo("All required artifacts present.")
