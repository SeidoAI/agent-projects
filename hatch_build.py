"""Hatchling build hook that bundles the React frontend into the wheel.

Runs during ``hatch build`` / ``uv build`` for the wheel target. Skipped
for editable installs (``uv pip install -e .``) so developer iteration
does not pay the npm-install cost on every install.

The actual build work lives in ``scripts/build_frontend.py`` so it can be
invoked directly by CI or developers without going through hatch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "frontend"

    def initialize(self, version: str, build_data: dict) -> None:
        # Hatchling passes "editable" for `pip install -e .` / `uv pip install -e .`.
        # Skip — editable installers mount the source tree directly and
        # developers can run the frontend dev server or invoke
        # scripts/build_frontend.py by hand.
        if version == "editable":
            return

        # Opt-out for packagers who build the static bundle themselves
        # (e.g. a CI job that already ran `npm run build` and just wants
        # `uv build` to pick up the existing files).
        if os.environ.get("TRIPWIRE_SKIP_FRONTEND_BUILD") == "1":
            return

        root = Path(self.root)
        script = root / "scripts" / "build_frontend.py"

        # Import the script so we run in-process and surface errors directly
        # rather than shelling out to a second Python.
        sys.path.insert(0, str(script.parent))
        try:
            import build_frontend  # type: ignore[import-not-found]

            build_frontend.build()
        finally:
            sys.path.pop(0)
