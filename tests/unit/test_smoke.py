"""Smoke test — verifies the package is importable and reports its version.

Replaced/supplemented by real unit tests in subsequent steps.
"""

import tripwire


def test_package_imports() -> None:
    assert tripwire.__version__ == "0.7.1"
