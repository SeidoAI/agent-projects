"""``tripwire session check`` — readiness + strict-tripwire punch list."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_check import strict_check
from tripwire.core.session_readiness import check_readiness


@session_cmd.command("check")
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
def session_check_cmd(session_id: str, project_dir: Path, output_format: str) -> None:
    """Report launch-readiness + strict-check tripwires for a session.

    No state transition. Two parallel views are returned:

    - **Readiness items** (artifact presence, blocked-by, handoff.yaml)
      from :func:`tripwire.core.session_readiness.check_readiness`.
    - **Strict tripwires** (placeholder content, repos overlap,
      effort/model mismatch) from
      :func:`tripwire.core.session_check.strict_check` — the gates
      ``session spawn`` enforces with no bypass.

    Exit code is non-zero when *either* surface has an error.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        report = check_readiness(resolved, session_id, kind="check")
        strict_results = strict_check(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    items = report.items
    errors = [i for i in items if not i.passing and i.severity == "error"]
    strict_errors = [r for r in strict_results if r.severity == "error"]
    strict_warnings = [r for r in strict_results if r.severity == "warning"]
    launch_ready = not errors and not strict_errors

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "session_id": session_id,
                    "launch_ready": launch_ready,
                    "items": [asdict(i) for i in items],
                    "strict_checks": [asdict(r) for r in strict_results],
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Readiness for {session_id}:\n")
        for item in items:
            mark = "✓" if item.passing else "✗"
            click.echo(f"  {mark} {item.label}")
            if not item.passing and item.fix_hint:
                click.echo(f"    → {item.fix_hint}")
        click.echo()
        if strict_results:
            click.echo("Strict checks (§A6):")
            for r in strict_results:
                mark = "✗" if r.severity == "error" else "!"
                click.echo(f"  {mark} {r.error_code}: {r.message}")
                if r.fix_hint:
                    click.echo(f"    → {r.fix_hint}")
            click.echo()
        if launch_ready:
            click.echo("Launch-ready.")
        else:
            blocking = len(errors) + len(strict_errors)
            warn_note = (
                f" ({len(strict_warnings)} warning(s) — non-blocking)"
                if strict_warnings
                else ""
            )
            click.echo(f"{blocking} must-fix. Not launch-ready.{warn_note}")
    if not launch_ready:
        raise click.exceptions.Exit(1)
