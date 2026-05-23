"""``tripwire session`` — session lifecycle and agenda operations.

Sessions live at ``sessions/<id>/session.yaml``.

This package replaces the former single-file ``cli/session.py``. The
Click group itself is defined in :mod:`tripwire.cli.session._group`;
each subcommand lives in its own module and registers itself on the
group at import time via ``@session_cmd.command(...)``. Shared helpers
live in :mod:`tripwire.cli.session._helpers`.

Subcommands (one per module):

- ``list`` — enumerate all sessions with status and issue counts
- ``show <id>`` — print one session's full YAML frontmatter + body
- ``check <id>`` — readiness punch list
- ``progress`` — task-checklist rollup across active sessions
- ``derive-branch <id>`` — print canonical branch name
- ``queue <id>`` — validate readiness, transition to queued
- ``spawn <id>`` — create worktree, launch claude -p, transition to executing
- ``batch-spawn`` — spawn N sessions with prompt-cache priming
- ``attach <id>`` — attach to a running runtime
- ``pause <id>`` — SIGTERM the claude process, transition to paused
- ``transition <id> <status>`` — generic workflow-executor transition
- ``abandon <id>`` — kill if running, transition to abandoned
- ``reopen <id>`` — move a completed session back to paused
- ``cleanup [<id>]`` — remove worktrees for completed/abandoned sessions
- ``scaffold <id>`` — render planning artifacts from Jinja templates
- ``logs <id>`` — show per-spawn log files
- ``summary <id>`` — summarise the latest stream-json log
- ``cost <id>`` — sum per-category token cost for a session
- ``analyze-routing`` — aggregate routing telemetry rows by route
- ``agenda`` — session dependency DAG with launch recommendations
- ``artifacts <id>`` — alias for ``tripwire project artifacts list <id>``
- ``log <id>`` — per-session JIT prompt fire log
- ``complete <id>`` — close-out orchestration (PR merged, issues closed)
- ``review <id>`` — review PR diff vs. issue specs
- ``prepare-review <id>`` — scaffold pr-review.yaml from member-issue ACs
- ``review-artifacts <id>`` — self-review.md + pm-response.yaml side by side
- ``monitor [<ids>]`` — one-shot runtime snapshot
- ``insights`` — sub-group: list/apply/reject agent node proposals
- Layer-1 wrappers: ``kill-runtime``, ``close-prs``, ``remove-worktrees``,
  ``flip-drafts-ready``, ``flip-drafts-draft``, ``normalise-branch``,
  ``followup-stub``
- Layer-2 chains: ``prepare-for-completion``, ``prepare-for-abandon``,
  ``sweep-issues-forward``
"""

from __future__ import annotations

# Re-exports for callers that still import from ``tripwire.cli.session``:
# - ``session_cmd`` — the Click group, registered by ``cli/main.py`` via
#   ``cli.add_command(session_cmd)``.
# - ``_resolve_clone_path`` — used by :mod:`tripwire.runtimes.prep` and
#   :mod:`tripwire.cli.validate_plan`; also patched by a handful of
#   unit tests that monkeypatch ``tripwire.cli.session._resolve_clone_path``
#   (the canonical home is now :mod:`tripwire.cli.session._helpers`, and
#   the spawn subcommand re-exports it under :mod:`tripwire.cli.session.spawn`).
# - ``SessionSummary`` — the dataclass exposed by ``session list``;
#   imported by the UI service layer for test fixtures and parallels.
# - ``subprocess`` / ``worktree_remove`` — re-exported so tests that
#   ``monkeypatch.setattr(cli_session, ...)`` against the old monolithic
#   module continue to work. The subcommand modules each import their
#   own ``subprocess`` / ``worktree_remove`` at module top-level, so
#   targeted patches on those submodules also work.
import subprocess

from tripwire.cli.session import abandon as _abandon_mod  # noqa: F401
from tripwire.cli.session import agenda as _agenda_mod  # noqa: F401
from tripwire.cli.session import (
    analyze_routing as _analyze_routing_mod,  # noqa: F401
)
from tripwire.cli.session import artifacts as _artifacts_mod  # noqa: F401
from tripwire.cli.session import attach as _attach_mod  # noqa: F401
from tripwire.cli.session import batch_spawn as _batch_spawn_mod  # noqa: F401
from tripwire.cli.session import check as _check_mod  # noqa: F401
from tripwire.cli.session import cleanup as _cleanup_mod  # noqa: F401
from tripwire.cli.session import close_prs as _close_prs_mod  # noqa: F401
from tripwire.cli.session import complete as _complete_mod  # noqa: F401
from tripwire.cli.session import cost as _cost_mod  # noqa: F401
from tripwire.cli.session import derive_branch as _derive_branch_mod  # noqa: F401
from tripwire.cli.session import (
    flip_drafts_draft as _flip_drafts_draft_mod,  # noqa: F401
)
from tripwire.cli.session import (
    flip_drafts_ready as _flip_drafts_ready_mod,  # noqa: F401
)
from tripwire.cli.session import followup_stub as _followup_stub_mod  # noqa: F401
from tripwire.cli.session import insights as _insights_mod  # noqa: F401
from tripwire.cli.session import kill_runtime as _kill_runtime_mod  # noqa: F401

# Subcommand modules: imported here purely for their side effect of
# registering ``@session_cmd.command(...)`` on the group. Order matches
# the original cli/session.py declaration order so ``--help`` listing
# stays byte-stable.
from tripwire.cli.session import list as _list_mod  # noqa: F401
from tripwire.cli.session import log as _log_mod  # noqa: F401
from tripwire.cli.session import logs as _logs_mod  # noqa: F401
from tripwire.cli.session import monitor as _monitor_mod  # noqa: F401
from tripwire.cli.session import (
    normalise_branch as _normalise_branch_mod,  # noqa: F401
)
from tripwire.cli.session import pause as _pause_mod  # noqa: F401
from tripwire.cli.session import (
    prepare_for_abandon as _prepare_for_abandon_mod,  # noqa: F401
)
from tripwire.cli.session import (
    prepare_for_completion as _prepare_for_completion_mod,  # noqa: F401
)
from tripwire.cli.session import (
    prepare_review as _prepare_review_mod,  # noqa: F401
)
from tripwire.cli.session import progress as _progress_mod  # noqa: F401
from tripwire.cli.session import queue as _queue_mod  # noqa: F401
from tripwire.cli.session import (
    remove_worktrees as _remove_worktrees_mod,  # noqa: F401
)
from tripwire.cli.session import reopen as _reopen_mod  # noqa: F401
from tripwire.cli.session import review as _review_mod  # noqa: F401
from tripwire.cli.session import (
    review_artifacts as _review_artifacts_mod,  # noqa: F401
)
from tripwire.cli.session import scaffold as _scaffold_mod  # noqa: F401
from tripwire.cli.session import show as _show_mod  # noqa: F401
from tripwire.cli.session import spawn as _spawn_mod  # noqa: F401
from tripwire.cli.session import summary as _summary_mod  # noqa: F401
from tripwire.cli.session import (
    sweep_issues_forward as _sweep_issues_forward_mod,  # noqa: F401
)
from tripwire.cli.session import transition as _transition_mod  # noqa: F401
from tripwire.cli.session import validate_plan as _validate_plan_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import (
    SessionSummary,
    _resolve_and_load_session,
    _resolve_clone_path,
)
from tripwire.core.git_helpers import worktree_remove

__all__ = [
    "SessionSummary",
    "_resolve_and_load_session",
    "_resolve_clone_path",
    "session_cmd",
    "subprocess",
    "worktree_remove",
]
