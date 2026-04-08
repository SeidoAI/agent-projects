"""Packaged default templates.

This is the tree that `agent-project init` copies into a new project. After
init, the project owns the copied templates — the package is no longer
canonical for them. Projects can add, remove, or reshape templates freely.

Call `get_templates_dir()` to locate the templates at runtime, regardless
of whether the package is installed editable or from a wheel.
"""

from __future__ import annotations

from pathlib import Path


def get_templates_dir() -> Path:
    """Return the absolute path to the packaged templates directory."""
    return Path(__file__).parent
