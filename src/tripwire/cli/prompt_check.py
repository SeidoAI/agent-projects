"""``tripwire prompt-check`` — record PM prompt-check invocations."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.events.log import emit_event
from tripwire.core.events.schema import EVENT_PROMPT_CHECK_INVOKED
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.registry import known_prompt_check_ids


@click.group(name="prompt-check")
def prompt_check_cmd() -> None:
    """Record workflow prompt-check events."""


@prompt_check_cmd.command("invoke")
@click.argument("prompt_check_id")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--workflow", default="coding-session", show_default=True)
@click.option(
    "--status",
    default=None,
    help="Target status this prompt-check satisfies. Inferred when unique.",
)
def prompt_check_invoke_cmd(
    prompt_check_id: str,
    session_id: str,
    project_dir: Path,
    workflow: str,
    status: str | None,
) -> None:
    """Record that PROMPT_CHECK_ID was invoked for SESSION_ID.

    ``workflow.yaml`` owns placement. The command refuses ids that are
    either not implemented as slash commands or not declared for the
    selected workflow/status, so a PM cannot accidentally satisfy a gate
    with a typo or a utility command.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    if prompt_check_id not in known_prompt_check_ids(resolved):
        raise click.ClickException(
            f"prompt-check {prompt_check_id!r} is not implemented"
        )

    session_yaml = resolved / "sessions" / session_id / "session.yaml"
    if not session_yaml.is_file():
        raise click.ClickException(f"session {session_id!r} not found")

    refs = _declared_prompt_check_refs(
        resolved,
        workflow=workflow,
        prompt_check_id=prompt_check_id,
    )
    if status is not None:
        refs = [ref for ref in refs if ref == status]
        if not refs:
            raise click.ClickException(
                f"prompt-check {prompt_check_id!r} is not declared for "
                f"{workflow!r}/{status!r} in workflow.yaml"
            )
        target_status = status
    elif len(refs) == 1:
        target_status = refs[0]
    elif not refs:
        raise click.ClickException(
            f"prompt-check {prompt_check_id!r} is not declared in workflow.yaml"
        )
    else:
        raise click.ClickException(
            f"prompt-check {prompt_check_id!r} is declared for multiple statuses "
            f"{refs}; pass --status"
        )

    emit_event(
        resolved,
        workflow=workflow,
        instance=session_id,
        status=target_status,
        event=EVENT_PROMPT_CHECK_INVOKED,
        details={"id": prompt_check_id},
    )
    click.echo(
        f"prompt-check: {prompt_check_id} invoked for {session_id} at "
        f"{workflow}/{target_status}"
    )


def _declared_prompt_check_refs(
    project_dir: Path,
    *,
    workflow: str,
    prompt_check_id: str,
) -> list[str]:
    spec = load_workflows(project_dir)
    refs: list[str] = []
    target = spec.workflows.get(workflow)
    if target is None:
        return refs
    for status in target.statuses:
        if prompt_check_id in status.prompt_checks:
            refs.append(status.id)
    return refs


__all__ = ["prompt_check_cmd"]
