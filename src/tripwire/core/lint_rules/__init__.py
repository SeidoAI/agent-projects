"""Lint rules registry — importing each submodule triggers @register_rule.

Import this package before running the linter so every rule gets
registered. ``src/tripwire/cli/lint.py`` does so at module load time.
"""

from . import (
    branch_convention,  # noqa: F401
    concept_drift,  # noqa: F401
    gap_analysis,  # noqa: F401
    session_stale,  # noqa: F401
    stale_workspace_nodes,  # noqa: F401
    unpushed_promotions,  # noqa: F401
    unresolved_merge_briefs,  # noqa: F401
)
