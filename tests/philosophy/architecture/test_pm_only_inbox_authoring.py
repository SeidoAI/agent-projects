"""The PM agent is the only inbox author. Framework code does not write.

Philosophy §6 ("The PM agent as attention curator") names this rule
twice — once with the load-bearing motivation, once with the explicit
non-writers:

    *"Validators don't auto-create inbox entries from lint failures.
    Coding agents don't escalate via inbox; their channels are PR
    descriptions, session artifacts, and (cross-container) the
    messaging layer. Scripts/cron/CI don't write inbox entries. The
    route layer has no POST-create endpoint."*

The motivation:

    *"Open-escalation channels degrade. Slack `@channel`
    notifications, JIRA notification streams, GitHub PR review
    queues — all started open and degraded into 'delete-without-
    reading' because the signal-to-noise ratio collapsed under the
    weight of many uncoordinated writers. Curated channels stay
    valuable because someone whose name is on the signal cares
    that it's worth reading."*

This test enforces the rule on the source tree. The only Python code
that may write to ``inbox/<id>.md`` is the resolve-mutation handler
in ``ui/services/inbox_service.py`` — and even that only updates
existing entries (the PM agent created them). Anywhere else in src/
that writes to inbox is a philosophy regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# The single allowed write-site. Its current implementation mutates
# existing entries (resolved=True flip) and does not create new ones.
# If a future change introduces creation here, the docstring and
# memory note about "PM agent is the only writer" need updating —
# but the philosophy doc explicitly carves out the resolve-flip as
# legitimate framework behaviour (an inbox entry's "resolved" field
# can be flipped by anyone who has eyes on it).
ALLOWED_WRITE_SITES = {
    SRC_ROOT / "ui" / "services" / "inbox_service.py",
}

# Patterns that look like writing to an inbox path. We focus on the
# canonical filename shape (``inbox/<id>.md`` or ``inbox_entry_path(...)``)
# so we catch the actual write rather than every mention of the word
# "inbox" in a comment.
INBOX_WRITE_PATTERNS = [
    re.compile(r"inbox_entry_path\([^)]*\)\.write"),
    re.compile(r"inbox_dir\([^)]*\)\s*/.*\.write"),
    re.compile(r'["\']inbox/[^"\']*\.md["\'].*write'),
    re.compile(r"atomic_write_text\([^,]*inbox"),
]


def test_no_framework_code_authors_inbox_entries():
    """Only ``ui/services/inbox_service.py`` may write to ``inbox/<id>.md``.

    Any other source file that writes there is a §6 regression: it
    means the framework is auto-escalating to the human, and §6's
    motivation (curated channel stays valuable; open channel
    degrades) gets eroded one writer at a time.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file in ALLOWED_WRITE_SITES:
            continue
        text = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern in INBOX_WRITE_PATTERNS:
                if pattern.search(line):
                    rel = py_file.relative_to(SRC_ROOT.parent)
                    violations.append(f"  {rel}:{line_no}: {line.strip()}")
                    break

    assert not violations, (
        "Philosophy §6 violation — framework code is writing to the\n"
        "inbox. The PM agent is the curated single writer; any other\n"
        "writer erodes the channel's signal/noise.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: if the framework genuinely needs the human's attention,\n"
        "the PM agent should write the entry. If the signal is\n"
        "structural (validator finding, lint failure), put it in the\n"
        "`tripwire validate` output and let the PM agent decide whether\n"
        "to escalate via inbox.\n"
        "See `docs/philosophy.md` §6 and `dec-pm-only-inbox-authoring`."
    )
