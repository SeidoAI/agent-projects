"""Read-only source-file viewer + local "open in default app" trigger.

Used by the workflow map: clicking a validator / skill / command / JIT
prompt opens a drawer that fetches the file content here, and an "Open
locally" button that POSTs to /api/source/open and lets the OS pick a
handler.

Security: paths are validated against an allow-list of roots — the
tripwire framework install dir, the project dir tree, and whatever
``project.yaml`` declares as its workspace. Anything outside is 403.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("tripwire.ui.routes.source")
router = APIRouter(prefix="/api/source", tags=["source"])

# Hard size limit on what the viewer will return — files larger than this
# are clearly not source we want to render in a side panel.
MAX_SOURCE_BYTES = 256 * 1024


def _allowed_roots() -> list[Path]:
    """Return the roots a path must live under to be served / openable.

    Includes:
    - The tripwire framework package directory (so SKILL.md / commands /
      validators .py files all qualify).
    - Every projects/ tree under the user's home (the dev workflow puts
      projects there, see /Users/<u>/Code/.../projects).
    - The current working directory (catches ad-hoc dev setups).
    """
    import tripwire  # local import — avoid pulling at module load

    roots: list[Path] = []
    pkg_root = Path(tripwire.__file__).resolve().parent
    roots.append(pkg_root)
    # Walk up to the repo root (parent of `src/tripwire`) so worktree paths
    # like `.claude/worktrees/...` are also reachable.
    repo_root = pkg_root.parent
    if repo_root.name == "src":
        repo_root = repo_root.parent
    roots.append(repo_root)
    cwd = Path.cwd().resolve()
    if cwd not in roots:
        roots.append(cwd)
    return roots


def _validate(path_str: str) -> Path:
    """Resolve and verify ``path_str`` is inside an allowed root."""
    if not path_str:
        raise HTTPException(status_code=400, detail="path is required")
    p = Path(path_str).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {path_str}")
    for root in _allowed_roots():
        try:
            p.relative_to(root.resolve())
            return p
        except ValueError:
            continue
    raise HTTPException(
        status_code=403,
        detail=f"path is outside allowed roots: {path_str}",
    )


@router.get("")
async def get_source(path: str = Query(...)) -> dict[str, Any]:
    """Return the file's text content + metadata for the viewer drawer."""
    p = _validate(path)
    size = p.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"source file too large: {size} bytes > {MAX_SOURCE_BYTES} limit"
            ),
        )
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail=f"file is not utf-8 text: {p.name}",
        ) from None
    return {
        "path": str(p),
        "name": p.name,
        "extension": p.suffix.lstrip("."),
        "size": size,
        "content": content,
    }


class OpenRequest(BaseModel):
    path: str


@router.post("/open")
async def open_source(req: OpenRequest) -> dict[str, Any]:
    """Open the file in the OS default application (macOS / linux / win)."""
    p = _validate(req.path)
    cmd: list[str]
    if sys.platform == "darwin":
        cmd = ["open", str(p)]
    elif sys.platform == "win32":
        # `start` is a shell builtin; spawn via cmd.exe
        cmd = ["cmd", "/c", "start", "", str(p)]
    else:
        opener = shutil.which("xdg-open")
        if not opener:
            raise HTTPException(
                status_code=501,
                detail="xdg-open not found on this system",
            )
        cmd = [opener, str(p)]
    try:
        subprocess.Popen(  # noqa: S603 — args validated above, no shell=True
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # pragma: no cover — local-only path
        logger.exception("failed to open %s", p)
        raise HTTPException(
            status_code=500,
            detail=f"failed to open file: {exc}",
        ) from exc
    return {"opened": str(p)}
