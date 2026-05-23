"""``tripwire session log`` — per-session JIT prompt fire log (KUI-99)."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd


@session_cmd.command("log")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--web",
    is_flag=True,
    default=False,
    help="Print a deep-link to the UI JIT Prompt Log filtered to this session.",
)
@click.option(
    "--reveal",
    is_flag=True,
    default=False,
    help="Reveal each fire's prompt body (PM-only).",
)
def session_log_cmd(
    session_id: str, project_dir: Path, web: bool, reveal: bool
) -> None:
    """Show all JIT prompt fires for a session, with timestamps and acks.

    Thin wrapper — see :func:`tripwire.core.session_log.enumerate_fires`.
    """
    from tripwire.cli._dev.jit_prompts import _is_pm
    from tripwire.core.session_log import enumerate_fires

    resolved = project_dir.expanduser().resolve()

    if web:
        click.echo(
            f"JIT Prompt Log: http://localhost:8000/jit-prompts?session_id={session_id}"
        )

    entries = list(enumerate_fires(resolved, session_id))
    if not entries:
        click.echo(f"No JIT prompt fires for session {session_id!r}.")
        return

    pm_mode = _is_pm()
    for entry in entries:
        if entry.unreadable:
            name = entry.source_path.name if entry.source_path else "?"
            click.echo(f"  <unreadable: {name}>")
            continue
        flag = " ESCALATED" if entry.escalated else ""
        click.echo(
            f"  {entry.fired_at}  {entry.jit_prompt_id}  on={entry.event}  "
            f"status={entry.ack_status}{entry.ack_detail}{flag}"
        )
        if reveal and pm_mode:
            body = entry.prompt_revealed or "(prompt not persisted)"
            indented = "\n".join("    " + line for line in body.splitlines())
            click.echo(indented)
