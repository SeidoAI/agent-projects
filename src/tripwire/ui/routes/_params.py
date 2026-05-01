"""Shared route parameter validators."""

from __future__ import annotations

import re

from tripwire.ui.routes._common import envelope_exception

_SESSION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
_SESSION_ID_RE = re.compile(_SESSION_ID_PATTERN)


def ensure_session_id(sid: str) -> None:
    """Reject path-like session IDs before service calls."""
    if not _SESSION_ID_RE.match(sid):
        raise envelope_exception(
            400,
            code="session/bad_slug",
            detail=(
                f"Session id {sid!r} does not match {_SESSION_ID_PATTERN} "
                "(alphanumeric first, then alphanumerics, underscores, or hyphens)."
            ),
        )


__all__ = ["ensure_session_id"]
