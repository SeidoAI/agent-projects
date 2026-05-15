"""Atomic file writes for mutation services.

All new-file writes in ``tripwire.ui.services`` (approval sidecars,
audit log entries) route through these helpers so the file watcher
cannot observe a half-written file. The two service-owned entity
writes — ``project.yaml`` in :mod:`~tripwire.ui.services.action_service`
and ``session.yaml`` in the same module — also use these helpers via
local ``_atomic_save_*`` wrappers that mirror the core
``save_project`` / ``save_session`` serialisation. Issue writes still
go through :func:`tripwire.core.store.save_issue` per the KUI-24
execution constraint; that helper does a direct ``path.write_text``
and is not yet atomic.

The mechanism is the classic ``write-to-temp → os.replace`` pattern:
``os.replace`` is guaranteed atomic on POSIX and on NTFS (since Python
3.3), so a concurrent reader either sees the old file or the complete
new one — never a torn payload.

The temp file is created in the same directory as the destination so
``os.replace`` is a same-filesystem rename (an atomic inode flip) rather
than a cross-device copy.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* via a same-directory tmp file + ``os.replace``.

    Creates parent directories if they don't exist. The tmp file name
    starts with ``.`` so partially-written files are invisible to any
    watcher globbing for ``*.yaml`` / ``*.md``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Clean up the tmp file on any failure so we don't leave debris.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically as UTF-8."""
    _atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_yaml(path: Path, data: Any) -> None:
    """Serialise *data* as YAML and write to *path* atomically.

    Uses ``safe_dump`` with block-style output and original key order so
    sidecar files read naturally when inspected by hand.
    """
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    atomic_write_text(path, text)


__all__ = ["atomic_write_text", "atomic_write_yaml"]
