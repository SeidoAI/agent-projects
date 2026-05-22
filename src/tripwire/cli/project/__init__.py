"""``tripwire project`` — project lifecycle operations.

New entity group introduced in v0.14.0 alongside the CLI reorg. Pulls
formerly top-level commands that operate on the project as a whole
under one namespace.

Subcommands (one per module):

- ``init [TARGET]`` — create a new tripwire project from packaged templates
- ``brief`` — front-load the agent's context (project config, enums,
  next IDs, etc.)
- ``readme generate`` — render or check the auto-generated README
"""

from __future__ import annotations

# Subcommand modules: imported here purely for their side effect of
# registering ``@project_cmd.command(...)`` on the group.
from tripwire.cli.project import brief as _brief_mod  # noqa: F401
from tripwire.cli.project import init as _init_mod  # noqa: F401
from tripwire.cli.project import readme as _readme_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.project._group import project_cmd
from tripwire.cli.project.brief import brief_cmd
from tripwire.cli.project.init import init_cmd
from tripwire.cli.project.readme import readme_cmd

__all__ = [
    "brief_cmd",
    "init_cmd",
    "project_cmd",
    "readme_cmd",
]
