"""UUID generation and validation helpers.

Every entity in the system carries a `uuid` field generated as a uuid4.
This module is a thin layer over the stdlib `uuid` module so the rest of
the codebase has a single import surface and so tests can monkey-patch the
generator if they need deterministic UUIDs.
"""

from __future__ import annotations

import uuid
from uuid import UUID


def generate_uuid() -> UUID:
    """Return a new uuid4. Wrap stdlib so tests can patch this one symbol."""
    return uuid.uuid4()


def is_valid_uuid(value: str | UUID) -> bool:
    """Return True if `value` is a syntactically valid UUID."""
    if isinstance(value, UUID):
        return True
    try:
        UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def coerce_uuid(value: str | UUID) -> UUID:
    """Convert a string or UUID to a UUID object.

    Raises:
        ValueError: if the value is not a valid UUID.
    """
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
