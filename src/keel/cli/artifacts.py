"""`keel artifacts list|show` — read session artifacts.

Session artifacts live at `sessions/<session-id>/artifacts/<file>`. The
set of required artifacts is declared in `templates/artifacts/manifest.yaml`
(see the Session Artifacts section of the plan). These commands are
read-only helpers so humans (and the UI) can browse what an agent has
produced for a given session.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

from keel.cli._utils import require_project as _require_project
from keel.core import paths

console = Console()

ARTIFACTS_SUBPATH = paths.SESSION_ARTIFACTS_SUBDIR
MANIFEST_REL = paths.TEMPLATES_ARTIFACTS_MANIFEST


@click.group(name="artifacts")
def artifacts_cmd() -> None:
    """Browse session artifacts (read-only)."""


@artifacts_cmd.command("list")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def artifacts_list(session_id: str, project_dir: Path, output_format: str) -> None:
    """List artifacts present for SESSION_ID, annotated with manifest status.

    Shows every file actually on disk under `sessions/<id>/artifacts/`,
    plus any required-but-missing entries from the manifest.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    artifacts_dir = paths.session_artifacts_dir(resolved, session_id)
    manifest = _load_manifest(resolved)

    rows: list[dict[str, str]] = []

    # Manifest entries first (so required-missing stay visible).
    manifest_files = {entry["file"] for entry in manifest}
    for entry in manifest:
        file = entry["file"]
        path = artifacts_dir / file
        rows.append(
            {
                "name": entry.get("name", Path(file).stem),
                "file": file,
                "required": "yes" if entry.get("required") else "no",
                "produced_at": entry.get("produced_at", ""),
                "exists": "yes" if path.exists() else "no",
            }
        )

    # Anything on disk not mentioned in the manifest → session-specific extras.
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            rel = str(path.relative_to(artifacts_dir))
            if rel not in manifest_files:
                rows.append(
                    {
                        "name": Path(rel).stem,
                        "file": rel,
                        "required": "no",
                        "produced_at": "(extra)",
                        "exists": "yes",
                    }
                )

    if output_format == "json":
        click.echo(json.dumps({"session": session_id, "artifacts": rows}, indent=2))
        return

    if not rows:
        console.print(
            f"[dim]session {session_id!r} has no artifacts and no manifest[/dim]"
        )
        return
    table = Table(title=f"Artifacts for {session_id}", show_header=True)
    table.add_column("name")
    table.add_column("file")
    table.add_column("required")
    table.add_column("produced_at")
    table.add_column("exists")
    for row in rows:
        exists_style = "green" if row["exists"] == "yes" else "red"
        table.add_row(
            row["name"],
            row["file"],
            row["required"],
            row["produced_at"],
            f"[{exists_style}]{row['exists']}[/{exists_style}]",
        )
    console.print(table)


@artifacts_cmd.command("show")
@click.argument("session_id")
@click.argument("artifact_name")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def artifacts_show(session_id: str, artifact_name: str, project_dir: Path) -> None:
    """Print the contents of one session artifact.

    ARTIFACT_NAME can be either the `name` field from the manifest (e.g.
    `plan`) or a relative filename (e.g. `plan.md`).
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    artifacts_dir = paths.session_artifacts_dir(resolved, session_id)
    if not artifacts_dir.is_dir():
        raise click.ClickException(
            f"No artifacts directory for session {session_id!r}: {artifacts_dir}"
        )

    # Resolve the name via the manifest first.
    manifest = _load_manifest(resolved)
    filename = artifact_name
    for entry in manifest:
        if entry.get("name") == artifact_name:
            filename = entry["file"]
            break

    candidate = artifacts_dir / filename
    if candidate.is_file():
        click.echo(candidate.read_text(encoding="utf-8"), nl=False)
        return

    # Second-pass: try matching by stem.
    matches = [
        p
        for p in artifacts_dir.rglob("*")
        if p.is_file() and (p.name == artifact_name or p.stem == artifact_name)
    ]
    if not matches:
        raise click.ClickException(
            f"Artifact {artifact_name!r} not found under {artifacts_dir}."
        )
    if len(matches) > 1:
        options = ", ".join(str(p.relative_to(artifacts_dir)) for p in matches)
        raise click.ClickException(
            f"Artifact name {artifact_name!r} is ambiguous: {options}"
        )
    click.echo(matches[0].read_text(encoding="utf-8"), nl=False)


# ============================================================================
# Helpers
# ============================================================================


def _load_manifest(project_dir: Path) -> list[dict]:
    """Return the list of artifact entries from `templates/artifacts/manifest.yaml`.

    Returns an empty list if the manifest is missing or malformed — the
    commands are expected to degrade gracefully when the project hasn't
    shipped a manifest yet.
    """
    manifest_path = project_dir / MANIFEST_REL
    if not manifest_path.exists():
        return []
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(raw, dict):
        return []
    entries = raw.get("artifacts", [])
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]
