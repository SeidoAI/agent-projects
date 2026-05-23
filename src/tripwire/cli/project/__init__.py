"""``tripwire project`` — project lifecycle operations.

Entity group expanded in v0.14.0 to host every command that operates
on the project as a whole. Pulls formerly top-level commands under one
namespace.

Subcommands (one per module):

- ``init [TARGET]`` — create a new tripwire project from packaged templates
- ``brief`` — front-load the agent's context (project config, enums,
  next IDs, etc.)
- ``readme generate`` — render or check the auto-generated README
- ``agenda`` — aggregated view of everything in flight
- ``status`` — dashboard summary
- ``refresh`` — rebuild the graph cache from the filesystem
- ``ui`` — start the Tripwire dashboard
- ``migrate`` — one-shot schema/layout migrations
- ``ci install`` — install the project-side CI workflow
- ``config`` — read / write ``~/.tripwire/config.yaml``
- ``hooks install`` — plant the Claude Code PostToolUse hook
- ``enums``, ``templates`` — browse project-owned configs
- ``events`` — read-only inspection of the workflow events log
- ``drift`` — coherence + workflow-drift findings
- ``heuristic`` — manage heuristic suppression markers
- ``artifacts`` — browse session artifacts
- ``validate`` — run the validation gate (also exposed as the
  top-level ``tripwire validate`` alias from ``cli/main.py``)
- ``lint`` — stage-aware heuristic checks
- ``next-key`` — atomic sequential key allocation
- ``plan`` — preview what ``init`` would produce
"""

from __future__ import annotations

# Subcommand modules: imported here purely for their side effect of
# registering ``@project_cmd.command(...)`` on the group.
from tripwire.cli.project import agenda as _agenda_mod  # noqa: F401
from tripwire.cli.project import artifacts as _artifacts_mod  # noqa: F401
from tripwire.cli.project import brief as _brief_mod  # noqa: F401
from tripwire.cli.project import ci as _ci_mod  # noqa: F401
from tripwire.cli.project import config as _config_mod  # noqa: F401
from tripwire.cli.project import drift as _drift_mod  # noqa: F401
from tripwire.cli.project import enums as _enums_mod  # noqa: F401
from tripwire.cli.project import events as _events_mod  # noqa: F401
from tripwire.cli.project import heuristic as _heuristic_mod  # noqa: F401
from tripwire.cli.project import hooks as _hooks_mod  # noqa: F401
from tripwire.cli.project import init as _init_mod  # noqa: F401
from tripwire.cli.project import lint as _lint_mod  # noqa: F401
from tripwire.cli.project import migrate as _migrate_mod  # noqa: F401
from tripwire.cli.project import next_key as _next_key_mod  # noqa: F401
from tripwire.cli.project import plan as _plan_mod  # noqa: F401
from tripwire.cli.project import readme as _readme_mod  # noqa: F401
from tripwire.cli.project import refresh as _refresh_mod  # noqa: F401
from tripwire.cli.project import status as _status_mod  # noqa: F401
from tripwire.cli.project import templates as _templates_mod  # noqa: F401
from tripwire.cli.project import ui as _ui_mod  # noqa: F401
from tripwire.cli.project import validate as _validate_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.project._group import project_cmd
from tripwire.cli.project.brief import brief_cmd
from tripwire.cli.project.hooks import hook_cmd
from tripwire.cli.project.init import init_cmd
from tripwire.cli.project.readme import readme_cmd
from tripwire.cli.project.validate import validate_cmd

__all__ = [
    "brief_cmd",
    "hook_cmd",
    "init_cmd",
    "project_cmd",
    "readme_cmd",
    "validate_cmd",
]
