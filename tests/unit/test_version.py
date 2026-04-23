"""Regression guard: `tripwire.__version__` must match `pyproject.toml`.

v0.7.2 shipped with a stale `__version__ = "0.7.1"` in
`src/tripwire/__init__.py` because no test asserted the two stayed
in sync. The CLI's `--version` reads `__version__`, so the drift
meant every 0.7.2 install reported itself as 0.7.1. This test
forces the next release to remember to bump both.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import tripwire

_PYPROJECT = Path(__file__).parent.parent.parent / "pyproject.toml"


def test_version_matches_pyproject():
    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert tripwire.__version__ == pyproject["project"]["version"], (
        f"tripwire.__version__={tripwire.__version__!r} but "
        f"pyproject.toml has version={pyproject['project']['version']!r}. "
        "Bump both when cutting a release."
    )


def test_version_is_pep440_parseable():
    """Extra-careful: make sure whatever we wrote isn't malformed."""
    if sys.version_info >= (3, 11):
        from importlib.metadata import version as _v

        # This resolves the *installed* dist version, which matches
        # pyproject.toml via setuptools/uv build.
        installed = _v("tripwire-pm")
        assert installed == tripwire.__version__
