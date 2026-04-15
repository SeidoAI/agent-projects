"""Smoke test — verifies the package is importable and reports its version.

Replaced/supplemented by real unit tests in subsequent steps.
"""

import keel


def test_package_imports() -> None:
    assert keel.__version__ == "0.6.0"
