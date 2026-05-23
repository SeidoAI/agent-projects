"""Click root group for `tripwire`.

Registers every v0 subcommand. The root group does nothing on its own —
all work happens inside the commands.

The CLI surface is organised by what each command OPERATES ON:

- ``session`` / ``issue`` / ``pr`` / ``node`` / ``project`` /
  ``workspace`` / ``inbox`` — entity groups; every command nests
  under its owning entity.
- ``_tools/`` (``gh``, ``git``), ``_utils/`` (``uuid``,
  ``completion``), ``_dev/`` (``jit-prompts``, ``test-jit-prompt``,
  ``prompt-check``), ``_cross/`` (``transition``) — internal
  organisation for files that don't belong to a single entity.
  Their commands still register at the root of the CLI (no
  ``_tools/_utils/_dev/_cross`` prefix in user-facing invocations).
- ``validate`` — top-level alias for ``project validate`` (the
  single most common command).
- ``hook`` — system entry point invoked by Claude Code via the
  ``.claude/settings.json`` PostToolUse hook. Stays at the root for
  back-compat with installed hook configs.
"""

from __future__ import annotations

import logging

import click

from tripwire import __version__
from tripwire.cli._cross.transition import transition_cmd
from tripwire.cli._dev.jit_prompts import jit_prompts_cmd
from tripwire.cli._dev.prompt_check import prompt_check_cmd
from tripwire.cli._dev.test_jit_prompt import test_jit_prompt_cmd
from tripwire.cli._tools.gh import gh_cmd
from tripwire.cli._tools.git import git_cmd
from tripwire.cli._utils.completion import completion_cmd
from tripwire.cli._utils.uuid_cmd import uuid_cmd
from tripwire.cli.inbox import inbox_cmd
from tripwire.cli.issue import issue_cmd
from tripwire.cli.node import node_cmd
from tripwire.cli.pr import pr_cmd
from tripwire.cli.project import project_cmd
from tripwire.cli.project.hooks import hook_cmd
from tripwire.cli.project.validate import validate_cmd as project_validate_cmd
from tripwire.cli.session import session_cmd
from tripwire.cli.workspace import workspace_cmd

# Verbose count → logging level. -v = INFO, -vv = DEBUG, default = WARNING.
LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


def _configure_logging(verbose: int) -> None:
    """Set the root logger level based on the -v count.

    Sets the level on the root logger directly so existing handlers (e.g.
    pytest's `caplog` handler) keep working. Only installs the default
    stderr handler if no handlers are configured yet.
    """
    level = LOG_LEVELS.get(min(verbose, 2), logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        root.addHandler(handler)


@click.group(
    help=(
        "Git-native project management with a concept graph for AI agents. "
        "The primary user is Claude Code (or similar) loaded with the "
        "project-manager skill; humans interact through the agent."
    )
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase logging verbosity. -v for INFO, -vv for DEBUG.",
)
@click.version_option(version=__version__, prog_name="tripwire")
@click.pass_context
def cli(ctx: click.Context, verbose: int) -> None:
    """Root command group. Does nothing on its own — see subcommands."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


# Entity groups.
cli.add_command(issue_cmd)
cli.add_command(pr_cmd)
cli.add_command(project_cmd)
cli.add_command(node_cmd)
cli.add_command(session_cmd)
cli.add_command(inbox_cmd)
cli.add_command(workspace_cmd)

# Top-level alias: `tripwire validate` → `tripwire project validate`.
# The same Click command object is re-registered at the root. Per user
# direction this is the ONLY top-level shortcut.
cli.add_command(project_validate_cmd, name="validate")

# System entry point: invoked by Claude Code via .claude/settings.json
# (PostToolUse hook). Stays at the root for back-compat with installed
# settings.json files.
cli.add_command(hook_cmd)

# Cross-cutting, dev, tool, and utility commands. Internally organised
# under cli/_cross/, cli/_dev/, cli/_tools/, cli/_utils/ — but each
# registers as a top-level command (no ``_cross/_dev/_tools/_utils``
# prefix in the user-facing invocation).
cli.add_command(transition_cmd)
cli.add_command(jit_prompts_cmd)
cli.add_command(prompt_check_cmd)
cli.add_command(test_jit_prompt_cmd)
cli.add_command(gh_cmd)
cli.add_command(git_cmd)
cli.add_command(uuid_cmd)
cli.add_command(completion_cmd)


if __name__ == "__main__":
    cli()
