"""Tests write only to ``tmp_path``.

Hygiene fitness function. The pytest convention is that every test
runs against a per-test temporary directory (``tmp_path`` /
``tmp_path_factory``). Tests that write to the developer's home
directory, the project tree itself, or any other persistent
location pollute the environment in ways that fail mysteriously
later — usually on a different developer's machine, or on CI where
the path doesn't exist.

This isn't a philosophy claim in ``docs/philosophy.md``, but it's an
operational claim of equal weight: tests are isolated; running them
leaves no trace. If a test fails to isolate, it's a bug — same as a
fitness function failure.

Detection scope:

We flag only the **unambiguously env-coupled** patterns:

  - ``Path.home()`` — resolves to the developer's actual home.
  - ``os.environ["HOME"]`` / ``os.getenv("HOME")`` — same thing
    via the env-var path.

We deliberately do NOT flag ``Path("/tmp/...")`` / ``"/home/..."``
string literals. ``Path("/tmp/foo")`` constructs a Path object
without touching disk; the literal might be inert test data
(passed to a model field, used in an assertion). Distinguishing
"value" from "filesystem touch" requires data-flow analysis that
isn't worth the maintenance cost for a hygiene check.

The narrower scope still catches the violations that matter:
:func:`Path.home` and env-anchored HOME lookups always intend to
reach a real on-disk location, regardless of surrounding syntax.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent.parent.parent


def _is_path_home_call(node: ast.AST) -> bool:
    """``Path.home()`` — ``Attribute(value=Name('Path'), attr='home')`` called."""
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "home":
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "Path"


def _is_home_env_lookup(node: ast.AST) -> bool:
    """``os.environ["HOME"]`` Subscript or ``os.getenv("HOME"...)`` /
    ``os.environ.get("HOME"...)`` Call."""
    if isinstance(node, ast.Subscript):
        target = node.value
        slice_val = node.slice
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "environ"
            and isinstance(target.value, ast.Name)
            and target.value.id == "os"
            and isinstance(slice_val, ast.Constant)
            and slice_val.value == "HOME"
        ):
            return True
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "HOME"
        ):
            return True
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "environ"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "HOME"
        ):
            return True
    return False


def test_tests_directory_does_not_anchor_to_home():
    """Every test in ``tests/`` avoids ``Path.home()`` calls and the
    equivalent ``os.environ["HOME"]`` / ``os.getenv("HOME")`` lookups.

    AST-based detection: we flag only actual CALLS / Subscript
    accesses, not string-literal mentions in docstrings or examples
    (the regex approach was tripped by the test files' own docstrings
    explaining the rule).
    """
    violations: list[str] = []
    for py_file in TESTS_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if _is_path_home_call(node) or _is_home_env_lookup(node):
                rel = py_file.relative_to(TESTS_ROOT.parent)
                violations.append(f"  {rel}:{node.lineno}")

    assert not violations, (
        "Test isolation violation — tests use `Path.home()` or\n"
        '`os.environ["HOME"]`, which reaches into the developer\'s\n'
        "real home directory and breaks under different layouts.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: use the `tmp_path` fixture. If the production code under\n"
        "test reads HOME (e.g. for `~/.tripwire/logs`), redirect via\n"
        "`monkeypatch.setenv('TRIPWIRE_LOG_DIR', str(tmp_path))` or the\n"
        "equivalent env-var override the code respects."
    )
