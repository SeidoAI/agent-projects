"""AST-based single-writer guarantee — catches the bypass shapes regex misses.

Philosophy §9 + the v0.13.1 C1-C3 cutover: every status mutation goes
through ``execute_transition``.

The regex-based companion test
(:mod:`tests/philosophy/architecture/test_single_writer_guarantee`)
catches the visible enum-typed pattern: ``obj.status = SessionStatus.PAUSED``. It doesn't catch:

  - ``setattr(obj, "status", SessionStatus.PAUSED)``
  - ``obj.__dict__["status"] = SessionStatus.PAUSED``
  - ``vars(obj)["status"] = SessionStatus.PAUSED``
  - ``obj.status = "completed"`` — string assignment, coerced into the
    typed enum by pydantic. This was the v0.13.2 follow-up finding:
    ``status_contract.sweep_issues`` wrote ``issue.status = target``
    (a string) for years, the regex pattern only matched
    ``IssueStatus.X``, the violation hid in plain sight.

All four shapes mutate the status field without tripping the regex.
A future agent (or an over-clever refactor) could route around the
single-writer guarantee via any of them.

This test walks the AST of every source file and asserts:

  1. No ``setattr(..., "status", ...)`` call.
  2. No ``Subscript`` assignment whose ``slice`` is ``"status"`` and
     whose target looks like ``obj.__dict__`` / ``vars(obj)``.
  3. No ``Assign`` whose target is ``<expr>.status``.

…all outside the executor and model definitions.

Pure-read AST analysis; no runtime cost beyond parse.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# Files allowed to perform any of these mutations. The executor is
# the single legitimate writer; model files define field defaults
# (those go through `__init__`, not the bypass shapes anyway).
ALLOWED_FILES = {
    SRC_ROOT / "core" / "workflow" / "transitions.py",
}
ALLOWED_DIRS = {SRC_ROOT / "models"}


def _is_allowed(path: Path) -> bool:
    if path in ALLOWED_FILES:
        return True
    return any(d in path.parents for d in ALLOWED_DIRS)


def _is_status_string(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "status"


def _is_dict_bypass_target(node: ast.expr) -> bool:
    """True if ``node`` is ``<expr>.__dict__`` or ``vars(<expr>)``."""
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "vars"
    ):
        return True
    return False


def _walk_violations(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield ``(lineno, description)`` for every bypass-shape mutation."""
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # setattr(obj, "status", ...) — only flag when the second arg
        # is the literal string "status"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "setattr" and len(node.args) >= 2:
                if _is_status_string(node.args[1]):
                    violations.append(
                        (
                            node.lineno,
                            "setattr(..., 'status', ...) bypasses execute_transition",
                        )
                    )
        # Assignment targets: obj.__dict__["status"] = ...,
        # vars(obj)["status"] = ..., or obj.status = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and _is_dict_bypass_target(target.value)
                    and _is_status_string(target.slice)
                ):
                    violations.append(
                        (
                            node.lineno,
                            "__dict__/vars()['status'] assignment bypasses executor",
                        )
                    )
                # `obj.status = ...` direct attribute write. The regex
                # sibling test catches `IssueStatus.X` RHS; this catches
                # string / variable / call RHS.
                #
                # Skip `self.status = ...` — that's the class-internal
                # constructor pattern (e.g. exception classes carry a
                # diagnostic `.status` attribute). The single-writer
                # concern is about WRITING ANOTHER object's status, not
                # an object initializing its own. We deliberately keep
                # the receiver-is-Name("self") case scoped to literal
                # `self` so `self.session.status = ...` (a real
                # violation routed through a nested attribute) still
                # flags.
                if isinstance(target, ast.Attribute) and target.attr == "status":
                    if not (
                        isinstance(target.value, ast.Name) and target.value.id == "self"
                    ):
                        violations.append(
                            (
                                node.lineno,
                                "direct `.status = ...` assignment bypasses executor",
                            )
                        )
    return violations


def test_no_setattr_or_dict_bypass_of_status_outside_executor():
    """Walk every source file's AST; assert no setattr / dict bypass
    of the ``status`` attribute exists outside the executor.

    This catches what the regex test (its sibling fitness function)
    can't see. Both tests must pass together — the regex finds the
    obvious shapes; this AST walk finds the sneaky ones.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if _is_allowed(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno, desc in _walk_violations(tree):
            rel = py_file.relative_to(SRC_ROOT.parent)
            violations.append(f"  {rel}:{lineno}: {desc}")

    assert not violations, (
        "Philosophy §9 / C1-C3 violation — AST-detected status mutation\n"
        "bypass found outside the executor. The regex test catches\n"
        "`obj.status = X`; this AST test catches the sneakier forms.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: route the mutation through `execute_transition` like every\n"
        "other status change. See `cli/session.py`'s queue / pause / fail\n"
        "commands for the canonical pattern. If you genuinely need a\n"
        "field that isn't a workflow status, name it something else."
    )
