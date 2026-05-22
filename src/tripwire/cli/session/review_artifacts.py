"""``tripwire session review-artifacts`` — self-review.md + pm-response.yaml side by side."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_store import load_session


@session_cmd.command("review-artifacts")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
    show_default=True,
    help="Output format. `human` is a terminal-friendly side-by-side view.",
)
def session_review_artifacts_cmd(
    session_id: str, project_dir: Path, output_format: str
) -> None:
    """Render sessions/<sid>/self-review.md + pm-response.yaml side by side.

    Marks self-review items that have no matching pm-response entry as
    unaddressed. Tolerates missing files — emits a clear hint when one
    side is absent rather than erroring out.
    """
    import json as _json
    from dataclasses import asdict

    from tripwire.core.session_review_artifacts import build_report

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    # load_session validates the session exists; we don't otherwise use it.
    load_session(resolved, session_id)

    report = build_report(resolved, session_id)

    if output_format == "json":
        click.echo(_json.dumps(asdict(report), indent=2, default=str))
        return

    # human format
    click.echo(f"Session review-artifacts: {session_id}")
    click.echo()

    if not report.self_review_present:
        click.echo("self-review.md missing — agent has not authored one yet.")
    if not report.pm_response_present:
        click.echo("pm-response.yaml missing — PM has not responded yet.")

    if report.self_review_present and not report.pairs:
        click.echo("self-review.md has no items under any `## Lens N:` heading.")

    for pair in report.pairs:
        click.echo(f"  Lens {pair.self_review_lens}: {pair.self_review_text}")
        if pair.pm_response is None:
            click.echo("    PM: (unaddressed)")
            continue
        decision = pair.pm_response.decision or "(no decision)"
        line = f"    PM [{decision}]"
        extras: list[str] = []
        if pair.pm_response.follow_up:
            extras.append(f"follow_up={pair.pm_response.follow_up}")
        if pair.pm_response.fix_commit:
            extras.append(f"fix_commit={pair.pm_response.fix_commit}")
        if extras:
            line += " (" + ", ".join(extras) + ")"
        click.echo(line)
        if pair.pm_response.note:
            click.echo(f"      → {pair.pm_response.note}")

    if report.unaddressed:
        click.echo()
        click.echo(
            f"{len(report.unaddressed)} unaddressed self-review item(s); "
            "PM should add quote_excerpt entries to pm-response.yaml."
        )
