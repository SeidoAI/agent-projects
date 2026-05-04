"""Git-native project management with concept graph for AI agents.

The primary user of this package is Claude Code (or similar agents) loaded
with the project-manager skill, not humans typing CLI commands. The CLI is
intentionally minimal: read commands, validation, and atomic operations.
Agents create issues, nodes, and sessions by writing files directly.

See https://github.com/SeidoAI/tripwire-workspace/blob/main/docs/tripwire-plan.md for the full design.
"""

__version__ = "0.9.6"
