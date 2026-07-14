"""``tripwire session followup-stub`` — append canonical PM follow-up stub to plan.md."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("followup-stub")
@click.argument("session_id")
@click.option(
    "--reason",
    default="",
    help="Reopen reason recorded in the PM follow-up section.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_followup_stub_cmd(session_id: str, reason: str, project_dir: Path) -> None:
    """Append the canonical PM follow-up stub to the session's plan.md.

    Resolves the plan path via :func:`paths.session_plan_path` (the
    canonical ``sessions/<sid>/artifacts/plan.md`` location). Idempotent
    — re-running once the stub is present is a clean no-op.
    """
    from tripwire.core import paths as _paths

    resolved, _ = _resolve_and_load_session(project_dir, session_id)

    plan_path = _paths.session_plan_path(resolved, session_id)
    if not plan_path.is_file():
        click.echo(
            f"session {session_id}: plan.md not found at {plan_path}",
            err=True,
        )
        return
    text = plan_path.read_text(encoding="utf-8")
    if "## PM follow-up" in text:
        click.echo(f"session {session_id}: PM follow-up section already present")
        return
    reason_str = reason or "<reason omitted>"
    appended = (
        f"\n\n## PM follow-up\n\n"
        f"Session reopened by PM. Reason: {reason_str}.\n\n"
        f"Re-engage the agent via `tripwire session spawn {session_id} --resume`.\n"
    )
    plan_path.write_text(text + appended, encoding="utf-8")
    click.echo(f"appended PM follow-up stub to {plan_path}")
