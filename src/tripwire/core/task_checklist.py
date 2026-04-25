"""Shared parser for ``task-checklist.md`` artifacts.

Used by both the CLI (``tripwire session progress``) and the UI service
(``session_service``) so the two surfaces report identical progress for
a given checklist file.

The canonical template (``templates/artifacts/task-checklist.md.j2``)
emits a Markdown table with a ``status`` column. Legacy projects that
still have checkbox-form (``- [ ]`` / ``- [x]``) checklists report
``done=0, total=0`` — they should migrate to the table format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskProgress:
    """Completed vs total rows parsed from ``task-checklist.md``."""

    done: int = 0
    total: int = 0


# Match a Markdown table row with a status cell.
# Example: `| #1 | Do thing | done |` → status = "done"
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*(?P<cols>.*?)\s*\|?\s*$")


def parse_task_checklist(text: str) -> TaskProgress:
    """Parse a ``task-checklist.md`` body into completed + total row counts.

    Expects a Markdown table — one row per task, with a ``status`` cell
    containing values like ``todo`` / ``in_progress`` / ``done``. The
    status enum is project-specific; we count ``done`` (case-insensitive)
    as complete. Header + separator lines are skipped.

    Returns ``TaskProgress(done=0, total=0)`` when the file has no
    recognisable rows (including legacy checkbox-form checklists).
    """
    done = 0
    total = 0

    table_rows: list[list[str]] = []
    for line in text.splitlines():
        m = _TABLE_ROW_RE.match(line)
        if m is None:
            continue
        cols = [c.strip() for c in m.group("cols").split("|")]
        # Separator rows like `|---|---|---|` have empty cells or dashes.
        if all(not c or set(c) <= {"-", ":"} for c in cols):
            continue
        table_rows.append(cols)

    if len(table_rows) >= 2:
        header = [c.lower() for c in table_rows[0]]
        data_rows = table_rows[1:]
        status_idx: int | None = None
        for i, h in enumerate(header):
            if h in {"status", "state"}:
                status_idx = i
                break
        if status_idx is None:
            status_idx = len(header) - 1

        for row in data_rows:
            if status_idx >= len(row):
                continue
            cell = row[status_idx].strip().lower()
            if not cell:
                continue
            total += 1
            if cell == "done":
                done += 1

    return TaskProgress(done=done, total=total)
