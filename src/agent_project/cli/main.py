"""Click root group for `agent-project`.

Registers every v0 subcommand. The root group does nothing on its own —
all work happens inside the commands.
"""

from __future__ import annotations

import logging

import click

from agent_project import __version__
from agent_project.cli.artifacts import artifacts_cmd
from agent_project.cli.completion import completion_cmd
from agent_project.cli.enums import enums_cmd
from agent_project.cli.graph import graph_cmd
from agent_project.cli.init import init_cmd
from agent_project.cli.next_key import next_key_cmd
from agent_project.cli.node import node_cmd
from agent_project.cli.refs import refs_cmd
from agent_project.cli.scaffold import scaffold_cmd
from agent_project.cli.status import status_cmd
from agent_project.cli.templates import templates_cmd
from agent_project.cli.validate import validate_cmd

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
@click.version_option(version=__version__, prog_name="agent-project")
@click.pass_context
def cli(ctx: click.Context, verbose: int) -> None:
    """Root command group. Does nothing on its own — see subcommands."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


cli.add_command(init_cmd)
cli.add_command(scaffold_cmd)
cli.add_command(next_key_cmd)
cli.add_command(validate_cmd)
cli.add_command(status_cmd)
cli.add_command(graph_cmd)
cli.add_command(refs_cmd)
cli.add_command(node_cmd)
cli.add_command(templates_cmd)
cli.add_command(enums_cmd)
cli.add_command(artifacts_cmd)
cli.add_command(completion_cmd)


if __name__ == "__main__":
    cli()
