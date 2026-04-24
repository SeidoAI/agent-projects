"""Branch naming convention for tripwire sessions.

Format: <type>/<session-slug> where:
- <type> is one of the project's active `branch_type` enum values. Defaults
  to feat/fix/refactor/docs/chore/test (shipped in `templates/enums/branch_type.yaml`);
  a project can override via `<project>/enums/branch_type.yaml`.
- <session-slug> is the session id minus any "session-" prefix,
  lowercase, hyphen-separated, ≤ `MAX_BRANCH_LENGTH` chars.

The convention is enforced at session launch (handoff.yaml.branch) and
checked by `tripwire lint handoff`. Sessions spanning multiple repos use the
same branch name across all repos.
"""

from __future__ import annotations

import re
from pathlib import Path

from tripwire.core.enum_loader import load_enum

_DEFAULT_TYPES: tuple[str, ...] = (
    "feat",
    "fix",
    "refactor",
    "docs",
    "chore",
    "test",
    # v0.7.4: `proj/<session-slug>` branches in the project-tracking
    # repo, cut per-session so parallel sessions don't race on
    # sessions/<id>/ or issues/<KEY>/developer.md writes.
    "proj",
)

# Legacy module-level constant kept for callers that read it (e.g. docstrings
# and error messages). Reflects the shipped default — projects with overrides
# should always pass `project_dir`.
ALLOWED_TYPES: tuple[str, ...] = _DEFAULT_TYPES

MAX_BRANCH_LENGTH = 60
SESSION_ID_PREFIX = "session-"

_BRANCH_PATTERN = re.compile(r"^([a-z]+)/([a-z0-9][a-z0-9\-]*)$")


class BranchNameError(ValueError):
    """Raised when a branch name doesn't match the convention."""


def is_valid_branch_shape(name: str) -> bool:
    """Return True iff `name` is shaped `<type>/<slug>` with slug rules — no type-list check.

    Used by model-level validators that don't have access to a project directory.
    Project-aware callers should prefer `is_valid_branch_name(..., project_dir=...)`.
    """
    if len(name) > MAX_BRANCH_LENGTH:
        return False
    m = _BRANCH_PATTERN.match(name)
    if m is None:
        return False
    branch_type, slug = m.group(1), m.group(2)
    if not branch_type:
        return False
    if not slug:
        return False
    return True


def _allowed_types(project_dir: Path | None) -> tuple[str, ...]:
    """Active branch types: project override → packaged default."""
    if project_dir is None:
        return _DEFAULT_TYPES
    try:
        values = load_enum(project_dir, "branch_type")
    except FileNotFoundError:
        return _DEFAULT_TYPES
    return tuple(values) if values else _DEFAULT_TYPES


def is_valid_branch_name(name: str, *, project_dir: Path | None = None) -> bool:
    """Return True iff `name` matches <type>/<slug> with allowed type."""
    if len(name) > MAX_BRANCH_LENGTH:
        return False
    m = _BRANCH_PATTERN.match(name)
    if m is None:
        return False
    branch_type, slug = m.group(1), m.group(2)
    if branch_type not in _allowed_types(project_dir):
        return False
    if not slug:
        return False
    return True


def parse_branch_name(name: str, *, project_dir: Path | None = None) -> tuple[str, str]:
    """Return (type, slug) from a valid branch name, else raise BranchNameError."""
    if not is_valid_branch_name(name, project_dir=project_dir):
        raise BranchNameError(
            f"branch '{name}' does not match <type>/<slug> with type in "
            f"{_allowed_types(project_dir)}"
        )
    m = _BRANCH_PATTERN.match(name)
    assert m is not None  # guarded by is_valid_branch_name
    return m.group(1), m.group(2)


def derive_branch_name(
    session_id: str,
    primary_issue_kind: str,
    *,
    project_dir: Path | None = None,
) -> str:
    """Build the canonical branch name from session id + primary issue kind.

    Normalises the session id to a branch slug:
    - strips any "session-" prefix
    - lowercases (git accepts uppercase but convention is lowercase,
      and session keys allocated via `tripwire next-key --type session`
      look like "TST-S1" — uppercase with hyphens)

    The kind must be one of the project's active branch types; other kinds
    (e.g. "epic") have no canonical branch and raise BranchNameError.
    """
    allowed = _allowed_types(project_dir)
    if primary_issue_kind not in allowed:
        raise BranchNameError(
            f"issue kind '{primary_issue_kind}' has no branch type "
            f"(allowed kinds: {allowed})"
        )
    slug = session_id.removeprefix(SESSION_ID_PREFIX).lower()
    candidate = f"{primary_issue_kind}/{slug}"
    if not is_valid_branch_name(candidate, project_dir=project_dir):
        raise BranchNameError(
            f"derived branch '{candidate}' invalid — session id "
            f"'{session_id}' must yield a hyphen-only slug after "
            "lowercasing and prefix stripping."
        )
    return candidate
