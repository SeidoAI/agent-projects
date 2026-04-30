"""`tripwire drift` — drift reporting CLI for the project.

Two subcommands, both shipped in v0.9:

- ``tripwire drift report`` (KUI-128 / A3) — single 0-100 coherence
  score with per-signal breakdown across stale pins, unresolved
  references, stale concept-node freshness, and recent
  workflow-drift events. Higher = healthier.

- ``tripwire drift findings`` (KUI-124) — list every workflow drift
  finding (missing required prompt-checks, tripwires that
  should-have-fired, unexpected transitions). Output is one finding
  per line as ``<code> <workflow>:<instance> <station?> :: <message>``
  so it pipes cleanly into agents and log greppers; exit non-zero on
  any finding.

Both subcommands consume `<project>/events/*.jsonl` (KUI-123 substrate)
when present; `report` aggregates into a score, `findings` prints
them. Future iterations will add ``--since`` for week-over-week deltas.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.drift import compute_coherence
from tripwire.core.store import ProjectNotFoundError, load_project
from tripwire.core.workflow.drift import detect_drift


@click.group(name="drift")
def drift_cmd() -> None:
    """Drift reporting for the project (coherence score + workflow gate findings)."""


@drift_cmd.command(name="report")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def report_cmd(project_dir: Path, output_format: str) -> None:
    """Render the coherence score (0-100) plus per-signal breakdown."""
    resolved = project_dir.expanduser().resolve()
    try:
        load_project(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    result = compute_coherence(resolved)

    if output_format == "json":
        click.echo(
            json.dumps(
                {"score": result.score, "breakdown": result.breakdown},
                indent=2,
            )
        )
        return

    click.echo(f"Coherence score: {result.score}/100")
    click.echo("")
    click.echo("Breakdown:")
    for name, count in result.breakdown.items():
        click.echo(f"  {name}: {count}")


@drift_cmd.command(name="findings")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--instance",
    default=None,
    help="Narrow to a single session id (events `instance` field).",
)
@click.option(
    "--workflow",
    "workflow_id",
    default="coding-session",
    show_default=True,
    help="Workflow id from workflow.yaml.",
)
def findings_cmd(project_dir: Path, instance: str | None, workflow_id: str) -> None:
    """Print workflow drift findings (KUI-124); exit non-zero on any."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    findings = detect_drift(resolved, instance=instance, workflow_id=workflow_id)
    if not findings:
        click.echo("no drift detected")
        return
    for f in findings:
        station = f.station or "-"
        click.echo(f"{f.code} {f.workflow}:{f.instance} {station} :: {f.message}")
    raise click.exceptions.Exit(code=1)


__all__ = ["drift_cmd"]
