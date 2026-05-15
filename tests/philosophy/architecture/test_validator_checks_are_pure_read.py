"""The whole validator tree is pure read.

Philosophy §3 ("Tripwires are agent-facing") makes validators the
*report* surface of the framework:

    *"Validators don't try to prevent the deviation — they catch it
    after. That asymmetry is the point."*

A validator that mutates state — writes a file, deletes a directory,
spawns a subprocess that does either — has moved out of the "report"
role and into the "act" role. That's a §3 violation.

History: round-3 of these tests *carved out* an exemption for
``apply_fixes`` (in ``core/validator/__init__.py``) and another for
``lint/no_orphan_proj_branches.py`` (raw ``subprocess.run`` for read-
only git queries). Both carve-outs were the show-pony pattern: the
test passes, but the philosophy violation remained. The correct
response was to fix the code:

  - ``apply_fixes`` moved to ``core/fix.py`` (Finding 1 fix).
  - Read-only git subprocess moved to ``core/git_helpers.py``
    (Finding 3 fix).

The validator tree (``core/validator/**``) is now mutation-free in
its entirety. This test enforces that: ``checks/``, ``lint/``, AND
``__init__.py`` are all scanned with no exemptions. A new mutation
anywhere under the tree is a §3 regression to fix at the source.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

VALIDATOR_ROOT = Path(tripwire.__file__).parent / "core" / "validator"

# Mutation patterns. Each is a regex matched against single lines of
# source (so a literal occurrence in a comment is fine; the test skips
# comment lines).
MUTATION_PATTERNS = [
    re.compile(r"\.write_text\("),
    re.compile(r"\.write_bytes\("),
    re.compile(r"\.unlink\("),
    re.compile(r"\.rmdir\("),
    re.compile(r"\.mkdir\("),
    re.compile(r"\.rename\("),
    re.compile(r"os\.remove\("),
    re.compile(r"shutil\.(rmtree|move|copy)"),
    re.compile(r"subprocess\.(run|Popen|call|check_output|check_call)"),
    # Note: `Path.replace()` (atomic rename) would be the dangerous
    # form, but `str.replace()` is harmless and far more common in
    # this codebase (template interpolation, etc.). We don't include
    # `.replace(` because static disambiguation is unreliable. If a
    # real `Path.replace()` mutation lands in a check, it gets caught
    # at code review.
]

# No exemptions. A failing test means the code drifted from intent;
# fix the code, not the test. (This used to carry an `EXEMPT_FILES`
# allowlist for `lint/no_orphan_proj_branches.py`; the proper §9 fix
# was to move its read-only `git` subprocess calls into
# `core/git_helpers.py`. The allowlist is gone and so is the inline
# subprocess.)


def _scan(root: Path) -> list[str]:
    """Return a list of `path:line: <line>` violation strings."""
    out: list[str] = []
    for py_file in root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            for pattern in MUTATION_PATTERNS:
                if pattern.search(line):
                    rel = py_file.relative_to(VALIDATOR_ROOT.parent.parent)
                    out.append(f"  {rel}:{line_no}: {line.strip()}")
                    break
    return out


def test_validator_tree_is_pure_read():
    """``core/validator/**.py`` — every file under the validator tree
    is mutation-free.

    Includes the top-level ``__init__.py`` (which previously held
    ``apply_fixes``; now extracted to ``core/fix.py``), the ``checks/``
    subdir, and the ``lint/`` subdir. Reads are fine; mutations and
    subprocess invocations are not.

    The §3-compatible pattern for "we want auto-correction when a
    check fires":
      1. The check returns a CheckResult (pure-read).
      2. The matching fix lives in ``core/fix.py``.
      3. ``validate_project(fix=True)`` orchestrates "read → fix → re-read".
    Mutation is partitioned to the fix module; the validator stays
    passive.
    """
    violations = _scan(VALIDATOR_ROOT)
    assert not violations, (
        "Philosophy §3 violation — a validator module is mutating state.\n"
        "The validator tree is the *report* surface; mutations live in\n"
        "`core/fix.py` and run via `validate_project(fix=True)`.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: if the mutation is a corrective fix, add it to\n"
        "`core/fix.py` (alongside the existing `_fix_uuid`,\n"
        "`_fix_timestamps`, etc.). If it's a read-only subprocess call,\n"
        "move it into the appropriate helper module (see\n"
        "`core/git_helpers.py` or `core/gh_helpers.py`)."
    )
