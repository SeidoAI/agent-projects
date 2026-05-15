"""``.tripwire/audit.jsonl`` is written only via the atomic helper.

Philosophy §7 ("Filesystem-native, file-watcher transport") makes the
audit log a load-bearing surface:

    *"Tripwire is git-native: every entity is a file, every change is
    a commit, every audit is `git log` or `git blame`."*

The transition audit log (`.tripwire/audit.jsonl`) is read by the UI
file-watcher, by human auditors, and by the PM agent on session
recovery. A torn write — half a JSON line landing on disk because a
crash interrupted ``Path.write_text`` mid-flush — corrupts every
downstream consumer.

``append_jsonl`` (in ``ui/services/_atomic_write.py``) writes via
tempfile + atomic rename so consumers either see a complete record or
no record. The §7 promise of "audit is `git log` or `git blame`" only
holds when every record is whole.

This test enforces the rule: any code path that targets
``audit.jsonl`` must route through the helper. Raw ``write_text``,
``open(..., 'w')``, or string concatenation onto the audit path is a
philosophy regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# Patterns that look like raw, non-atomic writes targeting the audit
# log. We match against literal "audit.jsonl" and against the helper
# names that compute its path. The atomic helper itself
# (``append_jsonl``) opens the path internally — that's the allowed
# write site.
RAW_WRITE_NEAR_AUDIT = [
    # `Path(...).write_text(...)` where the path mentions audit
    re.compile(r"audit.*\.write_text\("),
    # `open("...audit.jsonl"..., "w"...)` (or "a") — raw fileio
    re.compile(r'open\([^)]*audit\.jsonl[^)]*["\'][wa]'),
    # Pathlib `Path(...) / "audit.jsonl"` followed by direct .write*
    re.compile(r'"audit\.jsonl".*\.write'),
]

# Files allowed to mention audit.jsonl freely (the atomic helper and
# its callers compute the path / read for testing — no raw writes
# from them either, but we still scan).
INFORMATIONAL_ONLY = set()  # currently none — pattern lives in helper


def test_audit_log_writes_route_through_atomic_helper():
    """No raw ``write_text`` / ``open("...audit.jsonl", "w")`` exists
    in src/. The only writer is ``append_jsonl`` in
    ``ui/services/_atomic_write.py``, invoked from the executor's
    post-write hook.

    A direct write is a §7 regression: the file-watcher / human
    auditor / PM-agent recovery readers can see a torn record. The
    helper exists precisely so the philosophy claim ("every audit is
    `git log` or `git blame`") survives the crash case.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file in INFORMATIONAL_ONLY:
            continue
        text = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern in RAW_WRITE_NEAR_AUDIT:
                if pattern.search(line):
                    rel = py_file.relative_to(SRC_ROOT.parent)
                    violations.append(f"  {rel}:{line_no}: {line.strip()}")
                    break

    assert not violations, (
        "Philosophy §7 violation — raw write to audit.jsonl detected.\n"
        "The audit log MUST be appended via the atomic helper\n"
        "(`ui/services/_atomic_write.py::append_jsonl`) so consumers\n"
        "never see a torn record.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: replace the raw write with\n"
        "  from tripwire.ui.services._atomic_write import append_jsonl\n"
        "  append_jsonl(audit_path, {'timestamp': ..., 'action': ..., ...})\n"
        "See `core/workflow/side_effects.py::append_audit_record` for\n"
        "the canonical caller."
    )
