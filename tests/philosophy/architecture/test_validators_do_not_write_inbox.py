"""Validators are passive — they don't write inbox entries.

Philosophy §3 ("Tripwires are agent-facing") is explicit:

    *"Tripwires don't go in the dashboard's attention queue. They live
    on a dedicated process-quality screen ... The tripwire log is for
    retrospective process improvement, not real-time alerting."*

Philosophy §6 ("The PM agent as attention curator") tightens this
to a code-level rule:

    *"Validators don't auto-create inbox entries from lint failures."*

The asymmetry — validators report, PM curates — is the whole
control-loop design. If a validator could write inbox entries
directly, the carefully-curated PM channel becomes a generic alerting
stream and §6's "curated channels stay valuable" promise dies.

This test enforces the rule structurally: nothing under
``core/validator/`` (or under ``core/validator/checks/`` or
``core/validator/lint/``) writes to the inbox. The fitness check is
narrow on purpose — a broad "no validator imports inbox at all" would
catch read-only references too, which §6 doesn't forbid.

This complements :mod:`tests/philosophy/architecture/test_pm_only_inbox_authoring`,
which enforces the broader rule across the whole tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent
VALIDATOR_ROOT = SRC_ROOT / "core" / "validator"

# Any text that suggests writing to an inbox file (creating OR
# updating). The validator surface is supposed to *find*, not *act*.
INBOX_WRITE_PATTERNS = [
    re.compile(r"inbox_entry_path\b"),
    re.compile(r"inbox_dir\b"),
    re.compile(r'["\']inbox/'),
]


def test_validator_modules_do_not_touch_the_inbox_authoring_surface():
    """``core/validator/`` contains no reference to the inbox write
    surface (paths.inbox_entry_path / paths.inbox_dir / literal
    "inbox/" strings).

    Validators report findings via the return value (``CheckResult``);
    that's the contract. Reaching into the inbox to author an entry
    would route a structural signal directly to the human, bypassing
    the PM curator role §6 defines.
    """
    if not VALIDATOR_ROOT.exists():
        # Sanity check — if the validator directory moves, this test
        # silently passes. Better to fail loud.
        raise AssertionError(
            f"validator root not found at {VALIDATOR_ROOT} — this test's "
            f"path assumption is stale. Update SRC_ROOT/VALIDATOR_ROOT."
        )

    violations: list[str] = []
    for py_file in VALIDATOR_ROOT.rglob("*.py"):
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
        "Philosophy §3 + §6 violation — validator code references the\n"
        "inbox authoring surface. Validators MUST stay passive — return\n"
        "CheckResult; the PM agent decides whether a finding crosses the\n"
        "threshold to a human's attention.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: emit a CheckResult with the finding. If the finding warrants\n"
        "an inbox entry, the PM agent (running the project-manager skill)\n"
        "decides that — not the validator. See `docs/philosophy.md` §6."
    )
