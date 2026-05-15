"""Every ``~/.tripwire`` path in src/ has an env-var override.

Operational hygiene fitness function. ``tripwire`` writes a few
things to the user's home directory:

  - ``~/.tripwire/logs/<project_id>.log`` — audit log
  - ``~/.tripwire/config.yaml`` — UI configuration

Tests must be able to redirect these to ``tmp_path`` so they don't
pollute the developer's real ``~/.tripwire``. The convention is an
env-var override:

::

    override = os.environ.get("TRIPWIRE_LOG_DIR")
    root = Path(override) if override else Path.home() / ".tripwire" / "logs"

This test enforces the convention: any ``Path.home() / ".tripwire"``
construction in src/ must be preceded by an ``os.environ.get`` /
``os.getenv`` call against a ``TRIPWIRE_*`` env var on the same line
or one of the previous few lines. Without the override, tests can't
isolate, and CI runs accumulate real state in the actual ``$HOME``.

Out of scope (deliberately not flagged):

  - Tilde expansion via ``Path.home()`` for user-supplied paths
    (e.g. ``project_service.py:343`` resolves ``~`` in the user's
    config, where redirecting to tmp_path would break the feature).
  - Reads of external tools' config (e.g. ``~/.config/gh/hosts.yml``
    — that file isn't under our control).

This narrow scope intentionally flags only the ``.tripwire``-owned
paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# A `Path.home() / ".tripwire" / ...` construction — the cases that
# write to OUR home subdirectory.
TRIPWIRE_HOME_CONSTRUCTION = re.compile(r"Path\.home\(\)\s*/\s*[\"']\.tripwire[\"']")

# An env-var override lookup against a TRIPWIRE_* env var. The presence
# of this on a nearby line proves the home path is overridable.
ENV_OVERRIDE = re.compile(
    r"os\.environ(?:\.get)?\s*\(\s*[\"']TRIPWIRE_[A-Z_]+[\"']"
    r"|os\.getenv\s*\(\s*[\"']TRIPWIRE_[A-Z_]+[\"']"
)

# How far back to look for the env-var override. The canonical pattern
# uses it on the line immediately before the `Path.home()` call; we
# allow up to 5 lines of cushion for comments/blank lines.
LOOKBACK_LINES = 5


def test_tripwire_home_paths_have_env_var_overrides():
    """Every ``Path.home() / ".tripwire"`` in src/ is preceded by an
    ``os.environ.get("TRIPWIRE_*")`` override within the last few
    lines.

    The convention lets tests redirect the path to ``tmp_path`` via
    ``monkeypatch.setenv``. Without it, the test EITHER pollutes
    ``$HOME`` OR fails because the production path doesn't exist
    under the test user.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        lines = text.splitlines()
        for line_no, line in enumerate(lines, 1):
            if not TRIPWIRE_HOME_CONSTRUCTION.search(line):
                continue
            # Look back up to LOOKBACK_LINES for an env-var override.
            start = max(0, line_no - 1 - LOOKBACK_LINES)
            window = lines[start:line_no]
            if any(ENV_OVERRIDE.search(prev) for prev in window):
                continue
            rel = py_file.relative_to(SRC_ROOT.parent)
            violations.append(f"  {rel}:{line_no}: {line.strip()}")

    assert not violations, (
        "Test-isolation hygiene violation — src/ constructs a\n"
        '`~/.tripwire/...` path without an `os.environ.get("TRIPWIRE_*")`\n'
        "override on a nearby line. Without the override, tests can't\n"
        "redirect this path to `tmp_path` and end up either polluting the\n"
        "developer's real `~/.tripwire` or failing under a hermetic test\n"
        "user.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: wrap the construction with an env-var override. See\n"
        "`ui/services/_audit.py::audit_log_path` for the canonical pattern:\n"
        '  override = os.environ.get("TRIPWIRE_LOG_DIR")\n'
        '  root = Path(override) if override else Path.home() / ".tripwire" / "logs"\n'
        "Pick an env-var name that matches the resource ('TRIPWIRE_CONFIG_DIR'\n"
        "for config files, etc.)."
    )
