"""Every status mutation routes through ``execute_transition``.

Philosophy §9 promises ``tripwire validate`` as the single accountability
surface. That promise depends on a single-writer guarantee: every
status change goes through the executor's gate (validators → tripwires
→ prompt-checks → atomic write → event emission → audit record).

The v0.13.1 C1-C3 cutover removed 11 sites that were writing
``session.status =`` / ``issue.status =`` / ``node.status =`` directly,
bypassing the gate. This test pins that invariant in place: if a
future agent (or human) re-adds a direct mutation, the test fails
immediately and points them at the executor.

This is a **fitness function**: it grep-walks the source tree rather
than running the system. The cost is one regex scan per test run; the
benefit is catching drift at write-time instead of at the next
debugging session.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# Files where direct status assignment is legitimate:
#   - transitions.py: the executor itself; this IS the single writer
#   - models/*.py: dataclass / pydantic field defaults
#     (e.g. `status: SessionStatus = SessionStatus.PLANNED`)
ALLOWED_FILES = {
    SRC_ROOT / "core" / "workflow" / "transitions.py",
}
ALLOWED_DIRS = {
    SRC_ROOT / "models",  # field defaults, not runtime mutation
}

# The mutation patterns the C1-C3 cutover removed. Each captures
# `<obj>.status = <Enum>.<MEMBER>` — runtime field assignment of a
# typed enum value, the shape that bypasses execute_transition.
MUTATION_PATTERNS = [
    re.compile(r"\.status\s*=\s*SessionStatus\."),
    re.compile(r"\.status\s*=\s*IssueStatus\."),
    re.compile(r"\.status\s*=\s*NodeStatus\."),
]


def _is_allowed(path: Path) -> bool:
    if path in ALLOWED_FILES:
        return True
    return any(allowed in path.parents for allowed in ALLOWED_DIRS)


def test_no_direct_status_mutation_outside_executor():
    """v0.13.1 single-writer guarantee: status assignments live only in
    the executor and in model field defaults.

    A direct ``session.status = SessionStatus.PAUSED`` anywhere else
    bypasses ``execute_transition``'s gate — the validators don't run,
    no audit record is appended, no event is emitted. The C1-C3
    cutover removed every such site; this test keeps them gone.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if _is_allowed(py_file):
            continue
        text = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern in MUTATION_PATTERNS:
                if pattern.search(line):
                    rel = py_file.relative_to(SRC_ROOT.parent)
                    violations.append(f"  {rel}:{line_no}: {line.strip()}")
                    break

    assert not violations, (
        "Philosophy §9 violation — direct status mutation found outside the\n"
        "executor. Every status change MUST route through\n"
        "`tripwire.core.workflow.transitions.execute_transition` so the\n"
        "validator gate, audit record, and event emission run as one.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: replace `obj.status = SomeStatus.FOO` with\n"
        "  execute_transition(project_dir, workflow_id=..., \n"
        "                     instance_id=..., target_status='foo')\n"
        "See `cli/session.py`'s queue / pause / fail commands for the\n"
        "canonical pattern."
    )
