"""Click root group for `tripwire`.

Registers every v0 subcommand. The root group does nothing on its own —
all work happens inside the commands.
"""

from __future__ import annotations

import logging

import click

from tripwire import __version__
from tripwire.cli.agenda import agenda_cmd
from tripwire.cli.artifacts import artifacts_cmd
from tripwire.cli.ci import ci_cmd
from tripwire.cli.completion import completion_cmd
from tripwire.cli.enums import enums_cmd
from tripwire.cli.graph import graph_cmd
from tripwire.cli.init import init_cmd
from tripwire.cli.issue import issue_cmd
from tripwire.cli.lint import lint_cmd
from tripwire.cli.next_key import next_key_cmd
from tripwire.cli.node import node_cmd
from tripwire.cli.plan import plan_cmd
from tripwire.cli.pr_summary import pr_summary_cmd
from tripwire.cli.readme import readme_cmd
from tripwire.cli.refresh import refresh_cmd
from tripwire.cli.refs import refs_cmd
from tripwire.cli.scaffold import brief_cmd, scaffold_cmd
from tripwire.cli.session import session_cmd
from tripwire.cli.status import status_cmd
from tripwire.cli.templates import templates_cmd
from tripwire.cli.ui import ui_cmd
from tripwire.cli.uuid_cmd import uuid_cmd
from tripwire.cli.validate import validate_cmd
from tripwire.cli.validate_plan import validate_plan_cmd
from tripwire.cli.view import view_cmd
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


cli.add_command(agenda_cmd)
cli.add_command(init_cmd)
cli.add_command(issue_cmd)
cli.add_command(ci_cmd)
cli.add_command(brief_cmd)
cli.add_command(scaffold_cmd)  # hidden alias — prefer `brief`
cli.add_command(next_key_cmd)
cli.add_command(plan_cmd)
cli.add_command(pr_summary_cmd)
cli.add_command(readme_cmd)
cli.add_command(uuid_cmd)
cli.add_command(validate_cmd)
cli.add_command(validate_plan_cmd)
cli.add_command(lint_cmd)
cli.add_command(status_cmd)
cli.add_command(graph_cmd)
cli.add_command(refresh_cmd)
cli.add_command(refs_cmd)
cli.add_command(node_cmd)
cli.add_command(session_cmd)
cli.add_command(templates_cmd)
cli.add_command(enums_cmd)
cli.add_command(artifacts_cmd)
cli.add_command(completion_cmd)
cli.add_command(ui_cmd)
cli.add_command(view_cmd)
cli.add_command(workspace_cmd)


if __name__ == "__main__":
    cli()
