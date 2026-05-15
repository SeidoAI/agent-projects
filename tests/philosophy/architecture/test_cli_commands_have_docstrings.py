"""Every CLI command has a non-empty docstring / help text.

Philosophy §9 makes the CLI surface the agent's primary contract:

    *"Agents execute via CLI. Skill markdown documents what to do
    and why. CLI commands are the how."*

The skill markdown points agents to specific commands and expects
``tripwire <cmd> --help`` to be a real, usable explanation when the
agent needs more detail. An empty docstring breaks that contract:
the help output is blank, the agent has no in-band explanation, and
the skill-markdown reference becomes a dead end.

This fitness function walks the registered click command tree and
asserts every leaf command exposes a non-empty help string (either
via the ``help=`` decorator argument OR via a docstring on the
underlying callable). Empty groups (containers for subcommands) are
allowed without help — they exist for organisation, not invocation.
"""

from __future__ import annotations

import click


def _walk_commands(
    group: click.Group, prefix: str = ""
) -> list[tuple[str, click.Command]]:
    """Yield ``(qualified-name, command)`` for every leaf command."""
    out: list[tuple[str, click.Command]] = []
    for name, cmd in group.commands.items():
        full = f"{prefix} {name}".strip()
        if isinstance(cmd, click.Group):
            out.extend(_walk_commands(cmd, prefix=full))
        else:
            out.append((full, cmd))
    return out


def _command_help_text(cmd: click.Command) -> str:
    """Return the help text click would show for *cmd*. Click falls back
    to the callback's docstring when no explicit ``help=`` is set."""
    if cmd.help and cmd.help.strip():
        return cmd.help.strip()
    callback = cmd.callback
    if callback is not None and callback.__doc__:
        return callback.__doc__.strip()
    return ""


def test_every_registered_cli_command_has_help_text():
    """Every registered ``tripwire <…>`` leaf command exposes a
    non-empty help string.

    An agent that runs ``tripwire some-cmd --help`` should see prose
    explaining what the command does. Empty help breaks the §9 promise
    that the CLI codifies repetitive procedure — the procedure isn't
    discoverable if its surface is mute.
    """
    from tripwire.cli.main import cli

    violations: list[str] = []
    for name, cmd in _walk_commands(cli):
        if not _command_help_text(cmd):
            violations.append(f"  tripwire {name}")

    assert not violations, (
        "Philosophy §9 violation — CLI command has empty help text.\n"
        "Every leaf command must explain itself: either via the click\n"
        "decorator's `help=` argument or via a docstring on the callback.\n"
        "Empty help means the agent's `--help` lookup returns nothing.\n"
        "\n"
        "Commands with no help:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: add a short docstring to the callback function (most\n"
        "registered commands do this already). One sentence is plenty;\n"
        "the verbose details belong in skill markdown."
    )
