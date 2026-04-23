"""Smoke test — verifies the package is importable and reports a version.

The exact version is checked against pyproject.toml in
`test_version.py`; this smoke only asserts the module imported and
exposes a non-empty `__version__` string. Hard-coding the version
here caused v0.7.2 and v0.7.3 to require a one-line bump and the
change to drift from the one true source.
"""

import tripwire


def test_package_imports() -> None:
    assert isinstance(tripwire.__version__, str)
    assert tripwire.__version__
