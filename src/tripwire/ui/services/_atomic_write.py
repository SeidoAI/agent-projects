"""Atomic file writes for mutation services.

Every write path in ``tripwire.ui.services`` routes through one of these
helpers so that the file watcher cannot observe a half-written file.
The mechanism is the classic ``write-to-temp → os.replace`` pattern:
``os.replace`` is guaranteed atomic on POSIX and on NTFS (since Python
3.3), so a concurrent reader either sees the old file or the complete
new one — never a torn payload.

The temp file is created in the same directory as the destination so
``os.replace`` is a same-filesystem rename (an atomic inode flip) rather
than a cross-device copy.
"""

from __future__ import annotations

import json
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


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append *record* to *path* as one JSON line.

    Audit logs are append-only, so we use a single ``open(…, "a")``
    write. On POSIX, writes under ``PIPE_BUF`` (at least 512 bytes, in
    practice 4 KiB) are atomic with respect to concurrent appenders.
    An audit-log record is far under that ceiling.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=str) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


__all__ = ["append_jsonl", "atomic_write_text", "atomic_write_yaml"]
