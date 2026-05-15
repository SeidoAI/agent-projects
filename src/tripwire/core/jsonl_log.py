"""POSIX-append-atomic JSONL log helper.

Single helper used by every JSONL append site in the codebase
(audit, events, routing telemetry). The mechanism is plain
``open(..., "a").write(line + "\\n")``: on POSIX, writes under
``PIPE_BUF`` (≥ 512 bytes, ~4 KiB in practice) are atomic with respect
to concurrent appenders. Every JSONL record we write fits comfortably
under that ceiling, so a concurrent reader sees either zero, one, or
N complete lines — never a torn line.

The helper lives in ``core/`` (not ``ui/services/``) because audit
logs, events, and telemetry are all core concerns. ``append_jsonl``
previously sat inside ``ui/services/_atomic_write.py``, but that
module's name implies tempfile + rename — true atomic-write
semantics — whereas this helper uses kernel-level append atomicity.
Different mechanism, different home.

Callers that need cross-process serialisation (lock + write +
unlock) wrap their own ``project_lock`` around this call; the helper
itself doesn't lock because not every JSONL log needs serialisation
(telemetry's single-writer assumption, for example).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, record: Any, **dumps_kwargs: Any) -> None:
    """Append *record* to *path* as one JSON line.

    ``**dumps_kwargs`` are forwarded to :func:`json.dumps` so call
    sites can tune serialisation (``sort_keys``, ``separators``,
    ``ensure_ascii``, ``default``). The newline is appended by this
    helper.

    Creates parent directories if they don't exist. No lock — callers
    that need cross-process serialisation wrap their own.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, **dumps_kwargs) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


__all__ = ["append_jsonl"]
