"""``tripwire test-jit-prompt <id>`` — fire one JIT prompt against a fixture context.

Authoring tooling for project-team JIT prompt authors (KUI-136 / B2).
The command loads the project's JIT prompt registry, finds the named
prompt, instantiates a synthetic :class:`JitPromptContext`, and
prints the prompt that ``fire()`` would return. With ``--ack``, it
writes the standard substantive ack marker so the next run sees the
ack path resolved.

PM-only by the same role marker as ``tripwire jit-prompts`` — the
authoring loop is meant for the team designing process, not for
agents.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project


def _is_pm() -> bool:
    """Mirror of ``cli/jit_prompts.py:_is_pm`` to avoid a circular import."""
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
            "`tripwire test-jit-prompt` is PM-only. Set `TRIPWIRE_ROLE=pm` "
            "or write `pm` to `~/.tripwire/role` (or `$TRIPWIRE_HOME/role`) "
            "and re-run."
        )


_DEFAULT_SESSION_ID = "_test"
"""Default session id for ``test-jit-prompt``. Underscored so it can't
collide with a real session id (real ids never start with ``_``) and
filesystem-safe on Windows (the ack-marker filename is
``<jit-prompt-id>-<session-id>.json``; angle brackets are invalid on
NTFS)."""


@click.command("test-jit-prompt")
@click.argument("jit_prompt_id")
@click.option(
    "--session",
    "session_id",
    default=_DEFAULT_SESSION_ID,
    show_default=True,
    help="Session id used to seed the variation_index hash.",
)
@click.option(
    "--ack",
    "write_ack",
    is_flag=True,
    default=False,
    help="Write a substantive ack marker so subsequent fires don't block.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def test_jit_prompt_cmd(
    jit_prompt_id: str,
    session_id: str,
    write_ack: bool,
    project_dir: Path,
) -> None:
    """Fire ``JIT_PROMPT_ID`` against a synthetic context and print the prompt.

    Useful for iterating on prompt copy without spawning a real
    session. With ``--ack`` the command also writes the substantive
    ack marker (``fix_commits=["<test>"]``) so the ack path is
    exercised end-to-end.
    """
    from tripwire._internal.jit_prompts import JitPromptContext
    from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry
    from tripwire.core.jit_prompt_state import write_jit_prompt_ack_marker
    from tripwire.core.store import load_project

    _require_pm()

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    registry = load_jit_prompt_registry(resolved)
    by_id = {
        prompt.id: (event, prompt)
        for event, prompts in registry.items()
        for prompt in prompts
    }
    if jit_prompt_id not in by_id:
        known = ", ".join(sorted(by_id.keys())) or "(empty)"
        raise click.ClickException(
            f"unknown JIT prompt id {jit_prompt_id!r}; known: {known}"
        )

    project = load_project(resolved)
    project_slug = project.name.lower().replace(" ", "-")
    ctx = JitPromptContext(
        project_dir=resolved,
        session_id=session_id,
        project_id=project_slug,
    )

    _event, jit_prompt = by_id[jit_prompt_id]
    prompt = jit_prompt.fire(ctx)
    click.echo(prompt)

    if write_ack:
        marker = write_jit_prompt_ack_marker(
            project_dir=resolved,
            session_id=session_id,
            jit_prompt_id=jit_prompt_id,
            fix_commits=["<test>"],
            declared_no_findings=False,
        )
        click.echo(f"Wrote ack marker: {marker}")
