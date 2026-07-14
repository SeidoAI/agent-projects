"""`tripwire jit-prompts` — PM-side registry inspection.

Subcommands:

  * ``list`` — list registered JIT prompts for the project. ``--reveal``
    surfaces the prompt body (PM-only — sensitive surface).

The role gate is the same one the primitive spec calls for in §7:
``~/.tripwire/role`` (or ``$TRIPWIRE_HOME/role``) holding the literal
``pm``, OR the ``TRIPWIRE_ROLE=pm`` env var. Default is executor;
executor mode refuses the command. This is a semantic separator, not
a security boundary — an agent on the PM's machine inherits PM role.
"""

from __future__ import annotations

import os
from pathlib import Path

import click


def _is_pm() -> bool:
    """Read the role marker from env or `~/.tripwire/role`."""
    env_role = os.environ.get("TRIPWIRE_ROLE", "").strip().lower()
    if env_role == "pm":
        return True
    home = os.environ.get("TRIPWIRE_HOME") or os.path.expanduser("~/.tripwire")
    role_path = Path(home) / "role"
    if role_path.is_file():
        try:
            value = role_path.read_text(encoding="utf-8").strip().lower()
        except OSError:
            return False
        return value == "pm"
    return False


def _require_pm() -> None:
    if not _is_pm():
        raise click.ClickException(
            "`tripwire jit-prompts` is PM-only. Set `TRIPWIRE_ROLE=pm` "
            "or write `pm` to `~/.tripwire/role` (or "
            "`$TRIPWIRE_HOME/role`) and re-run."
        )


@click.group("jit-prompts")
def jit_prompts_cmd() -> None:
    """PM-side JIT prompt registry inspection."""


@jit_prompts_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--reveal",
    is_flag=True,
    default=False,
    help="Reveal each JIT prompt body (PM-only; content is sensitive).",
)
def jit_prompts_list_cmd(project_dir: Path, reveal: bool) -> None:
    """List registered JIT prompts for the project."""
    from tripwire._internal.jit_prompts import JitPromptContext
    from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry

    _require_pm()

    resolved = project_dir.expanduser().resolve()
    registry = load_jit_prompt_registry(resolved)
    if not registry:
        click.echo("JIT prompts are disabled for this project (no prompts registered).")
        return

    # Synthetic context for prompt rendering when --reveal is set.
    # The session_id is a placeholder — variation choice is by
    # (project_id, session_id) hash, so this gives a deterministic
    # "default" view without needing an actual session.
    ctx = JitPromptContext(
        project_dir=resolved, session_id="<inspection>", project_id="<inspection>"
    )

    rows = 0
    for event in sorted(registry):
        for jit_prompt in registry[event]:
            rows += 1
            click.echo(
                f"  {jit_prompt.id}  fires_on={event}  blocks={jit_prompt.blocks}"
            )
            if reveal:
                try:
                    prompt = jit_prompt.fire(ctx)
                except Exception as exc:  # pragma: no cover — defensive
                    click.echo(f"    <error rendering prompt: {exc}>")
                    continue
                indented = "\n".join("    " + line for line in prompt.splitlines())
                click.echo(indented)
    if rows == 0:
        click.echo("(registry empty — only project-local extras would appear)")
