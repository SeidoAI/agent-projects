"""Sequential `<PREFIX>-<N>` key generation.

The actual atomic allocation under a file lock lives in `key_allocator.py`.
This module is the pure functional layer: given a prefix and a number, it
formats the key; given a key, it parses it back.
"""

from __future__ import annotations

import re

KEY_PATTERN = re.compile(r"^([A-Z][A-Z0-9]*)-(\d+)$")


def format_key(prefix: str, number: int) -> str:
    """Format a sequential key from a prefix and a number.

    Examples:
        format_key("SEI", 42)  # -> "SEI-42"
    """
    if not prefix:
        raise ValueError("Prefix must be non-empty.")
    if not prefix[0].isupper() or not prefix.replace("_", "").isalnum():
        raise ValueError(
            f"Prefix {prefix!r} must start with an uppercase letter and contain "
            f"only uppercase letters and digits."
        )
    if number < 1:
        raise ValueError(f"Key number must be >= 1, got {number}.")
    return f"{prefix}-{number}"


def parse_key(key: str) -> tuple[str, int]:
    """Parse a sequential key into (prefix, number).

    Examples:
        parse_key("SEI-42")  # -> ("SEI", 42)

    Raises:
        ValueError: if the key does not match the expected format.
    """
    match = KEY_PATTERN.match(key)
    if not match:
        raise ValueError(
            f"Key {key!r} does not match the expected format <PREFIX>-<N>. "
            f"Pattern: {KEY_PATTERN.pattern}"
        )
    prefix, number_str = match.groups()
    return prefix, int(number_str)


def is_valid_key(key: str) -> bool:
    """Return True if `key` matches the expected `<PREFIX>-<N>` format."""
    return bool(KEY_PATTERN.match(key))
