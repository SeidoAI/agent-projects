"""Every member issue at-or-past ``verified`` must ship ``verified.md``."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _issue_artifacts_for_session


def check_session_has_verified_md(ctx: ValidationContext) -> list[CheckResult]:
    """Every member issue of a session at-or-past verified must have
    its `verified.md` artifact on disk.

    Code: ``session/verified_md_missing``.
    """
    return _issue_artifacts_for_session(ctx, "verified")
