"""Validator checks/lint subdirs are pure read.

Philosophy §3 ("Tripwires are agent-facing") makes validators the
*report* surface of the framework:

    *"Validators don't try to prevent the deviation — they catch it
    after. That asymmetry is the point."*

A validator that mutates state — writes a file, deletes a directory,
spawns a subprocess that does either — has moved out of the "report"
role and into the "act" role. That's a §3 violation.

But there's a documented carve-out: ``tripwire validate --fix`` does
mutate. The fix path lives in ``core/validator/__init__.py`` (top-
level module) and is invoked separately from the check pipeline. The
checks themselves stay pure-read; the fixer is a sibling concept.

This test enforces the actual rule: ``core/validator/checks/`` and
``core/validator/lint/`` (the directories containing check / heuristic
implementations) MUST NOT contain filesystem-mutating calls. The
top-level ``core/validator/__init__.py`` is allowed to mutate — that's
where ``apply_fixes`` lives.

If a future change introduces a check that "auto-fixes" inline (mutates
during the check) rather than going through ``apply_fixes``, the
fix-as-side-effect-of-reporting drift trips this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

VALIDATOR_ROOT = Path(tripwire.__file__).parent / "core" / "validator"
CHECKS_DIR = VALIDATOR_ROOT / "checks"
LINT_DIR = VALIDATOR_ROOT / "lint"

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

# Files allowed to mutate despite the rule. Each entry needs a
# comment explaining why. The exemption is a debt, not a discharge:
# the long-term §3-pure pattern is to put subprocess plumbing in a
# `_helpers` module (cf. `core/gh_helpers.py`) and have the lint
# call the helper instead.
EXEMPT_FILES: dict[Path, str] = {
    # KUI: v0.13.1 deferral #2 consolidated `gh` subprocess plumbing
    # into `core/gh_helpers.py`. The equivalent for `git` is a follow-
    # up: `no_orphan_proj_branches.py` makes read-only `git for-each-
    # ref` / `git rev-list` calls inline. The subprocess invocations
    # are READ-only (capture_output=True, no mutation flags), so
    # they don't violate §3 in spirit — but the §9 "CLI codifies
    # repetitive procedure" principle says they should live in a
    # `core/git_helpers.py`-style module, not inline in the lint.
    LINT_DIR / "no_orphan_proj_branches.py": (
        "v0.13.1 follow-up: read-only git subprocess should move to core/git_helpers.py"
    ),
}


def _scan(root: Path) -> list[str]:
    """Return a list of `path:line: <line>` violation strings."""
    out: list[str] = []
    for py_file in root.rglob("*.py"):
        if py_file in EXEMPT_FILES:
            continue
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


def test_validator_checks_subdir_is_pure_read():
    """``core/validator/checks/**.py`` performs no filesystem
    mutation. Reads are fine; subprocess invocations are not.

    If a check needs to mutate, the §3-compatible pattern is:
      1. Report the finding (return a CheckResult).
      2. Wire the matching fix into ``apply_fixes`` in
         ``core/validator/__init__.py``.
    That separates "report" from "act" at the module boundary.
    """
    violations = _scan(CHECKS_DIR)
    assert not violations, (
        "Philosophy §3 violation — a validator check is mutating state.\n"
        "Checks must be pure-read. Mutations belong in `apply_fixes`\n"
        "(in `core/validator/__init__.py`), not in individual checks.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: return a CheckResult; add the corresponding fix to\n"
        "`apply_fixes` so the `--fix` flag picks it up. See the existing\n"
        "`_bump_next_issue_number` fixer for the canonical pattern."
    )


def test_validator_lint_subdir_is_pure_read():
    """``core/validator/lint/**.py`` performs no filesystem mutation.

    Heuristic / lint checks are advisory by design — they MUST NOT
    take corrective action themselves.
    """
    violations = _scan(LINT_DIR)
    assert not violations, (
        "Philosophy §3 violation — a lint heuristic is mutating state.\n"
        "Heuristics are advisory; they emit findings, never act.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: emit a warning-severity CheckResult. If the lint truly\n"
        "needs an auto-fix, promote it to a check + `apply_fixes` row."
    )
