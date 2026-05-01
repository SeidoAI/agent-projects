"""Build the React frontend and place the output where the wheel will pick it up.

Runs ``npm ci`` + ``npm run build`` inside ``web/``.
Vite is already configured (``build.outDir: '../src/tripwire/ui/static'`` in
``vite.config.ts``) to write the bundle into ``src/tripwire/ui/static/``,
so no copy step is needed here.

This script is invoked in two places:

1. Directly by developers and CI: ``python scripts/build_frontend.py``.
2. Indirectly by the hatch build hook in ``hatch_build.py`` when building
   the wheel via ``uv build`` / ``hatch build``.

Keeping it as a standalone module (stdlib only) means the hook can import
and call it without pulling build-time dependencies into the wheel.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "web"
STATIC_DIR = REPO_ROOT / "src" / "tripwire" / "ui" / "static"


def _require_npm() -> str:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm not found on PATH. Install Node.js 20+ (see "
            "https://nodejs.org) before building the frontend bundle."
        )
    return npm


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _human_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def build() -> None:
    """Install frontend deps and produce the production bundle in ``static/``."""
    if not FRONTEND_DIR.is_dir():
        raise RuntimeError(f"Frontend source not found at {FRONTEND_DIR}")

    npm = _require_npm()

    print(f"→ npm ci (in {FRONTEND_DIR.relative_to(REPO_ROOT)})", flush=True)
    subprocess.run([npm, "ci"], cwd=FRONTEND_DIR, check=True)

    print(f"→ npm run build (output: {STATIC_DIR.relative_to(REPO_ROOT)})", flush=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)

    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise RuntimeError(
            f"Build completed but {index} is missing. "
            "Check vite.config.ts build.outDir."
        )

    size = _dir_size(STATIC_DIR)
    print(
        f"✓ Frontend bundle ready at {STATIC_DIR.relative_to(REPO_ROOT)} "
        f"({_human_size(size)})",
        flush=True,
    )


def main() -> int:
    try:
        build()
    except subprocess.CalledProcessError as exc:
        print(f"✗ Frontend build failed: {exc}", file=sys.stderr)
        return exc.returncode or 1
    except RuntimeError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
