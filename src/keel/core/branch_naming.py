"""Branch naming convention for keel sessions.

Format: <type>/<session-slug> where:
- <type> is one of ALLOWED_TYPES (feat, fix, refactor, docs, chore, test),
  derived from the session's primary issue kind.
- <session-slug> is the session id minus any "session-" prefix,
  lowercase, hyphen-separated, ≤ `MAX_BRANCH_LENGTH` chars.

The convention is enforced at session launch (handoff.yaml.branch) and
checked by `keel lint handoff`. Sessions spanning multiple repos use the
same branch name across all repos.
"""

from __future__ import annotations

import re

ALLOWED_TYPES: tuple[str, ...] = ("feat", "fix", "refactor", "docs", "chore", "test")
MAX_BRANCH_LENGTH = 60
SESSION_ID_PREFIX = "session-"

_BRANCH_PATTERN = re.compile(r"^([a-z]+)/([a-z0-9][a-z0-9\-]*)$")


class BranchNameError(ValueError):
    """Raised when a branch name doesn't match the convention."""


def is_valid_branch_name(name: str) -> bool:
    """Return True iff `name` matches <type>/<slug> with allowed type."""
    if len(name) > MAX_BRANCH_LENGTH:
        return False
    m = _BRANCH_PATTERN.match(name)
    if m is None:
        return False
    branch_type, slug = m.group(1), m.group(2)
    if branch_type not in ALLOWED_TYPES:
        return False
    if not slug:
        return False
    return True


def parse_branch_name(name: str) -> tuple[str, str]:
    """Return (type, slug) from a valid branch name, else raise BranchNameError."""
    if not is_valid_branch_name(name):
        raise BranchNameError(
            f"branch '{name}' does not match <type>/<slug> with type in {ALLOWED_TYPES}"
        )
    m = _BRANCH_PATTERN.match(name)
    assert m is not None  # guarded by is_valid_branch_name
    return m.group(1), m.group(2)


def derive_branch_name(session_id: str, primary_issue_kind: str) -> str:
    """Build the canonical branch name from session id + primary issue kind.

    Normalises the session id to a branch slug:
    - strips any "session-" prefix
    - lowercases (git accepts uppercase but convention is lowercase,
      and session keys allocated via `keel next-key --type session`
      look like "TST-S1" — uppercase with hyphens)

    The kind must be one of ALLOWED_TYPES; other kinds (e.g. "epic")
    have no canonical branch and raise BranchNameError.
    """
    if primary_issue_kind not in ALLOWED_TYPES:
        raise BranchNameError(
            f"issue kind '{primary_issue_kind}' has no branch type "
            f"(allowed kinds: {ALLOWED_TYPES})"
        )
    slug = session_id.removeprefix(SESSION_ID_PREFIX).lower()
    candidate = f"{primary_issue_kind}/{slug}"
    if not is_valid_branch_name(candidate):
        raise BranchNameError(
            f"derived branch '{candidate}' invalid — session id "
            f"'{session_id}' must yield a hyphen-only slug after "
            "lowercasing and prefix stripping."
        )
    return candidate
