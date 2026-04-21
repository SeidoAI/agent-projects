"""``tripwire lint`` — stage-aware heuristic checks.

Distinct from ``tripwire validate``: validate is mechanical
(schema/refs/graph consistency); lint is heuristic (did someone
actually do the work at each stage).

Stages:
- ``scoping`` — ran during /pm-scope or /pm-rescope
- ``handoff`` — before /pm-session-queue
- ``session`` — in-flight health of one session

Exit codes follow ``linter.exit_code_for``: 0 (info-only),
1 (warning present), 2 (error present).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project

# Importing the rules package triggers @register_rule for each rule.
from tripwire.core import lint_rules  # noqa: F401
from tripwire.core.linter import Linter, exit_code_for


@click.group(name="lint")
def lint_cmd() -> None:
    """Heuristic checks (distinct from `tripwire validate`)."""


@lint_cmd.command("scoping")
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
def lint_scoping(project_dir: Path, output_format: str) -> None:
    """Run scoping-stage lint rules."""
    _run_stage("scoping", project_dir, output_format)


@lint_cmd.command("handoff")
@click.argument("session_id", required=False)
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
def lint_handoff(session_id: str | None, project_dir: Path, output_format: str) -> None:
    """Run handoff-stage lint rules (optionally for one session)."""
    _run_stage("handoff", project_dir, output_format, session_id=session_id)


@lint_cmd.command("session")
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
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def lint_session(session_id: str, project_dir: Path, output_format: str) -> None:
    """Run session-stage lint rules for one session."""
    _run_stage("session", project_dir, output_format, session_id=session_id)


def _run_stage(
    stage: str,
    project_dir: Path,
    output_format: str,
    session_id: str | None = None,
) -> None:
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    linter = Linter(project_dir=resolved, session_id=session_id)
    findings = list(linter.run_stage(stage))

    if output_format == "json":
        click.echo(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            click.echo(f"No {stage} findings.")
        else:
            for f in findings:
                click.echo(f"  [{f.severity}] {f.code}: {f.file}")
                click.echo(f"    {f.message}")
                if f.fix_hint:
                    click.echo(f"    → {f.fix_hint}")

    raise click.exceptions.Exit(exit_code_for(findings))
