"""Tests for `tripwire hook validate-on-edit` (KUI-110 Phase 1.1).

The hook is a Claude Code PostToolUse handler. It reads a JSON envelope
from stdin, walks up to find the project root, runs the validator
in-process, and emits a `decision: "block"` JSON to stdout if validation
errors were found. All defensive paths exit 0 silently so unrelated
agent work isn't broken by hook misbehaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


def _write_minimal_project(project_dir: Path) -> None:
    """Bootstrap a directory so it parses as a tripwire project."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "fixture",
                "key_prefix": "FIX",
                "base_branch": "main",
                "next_issue_number": 1,
                "next_session_number": 1,
            }
        ),
        encoding="utf-8",
    )


def _hook_input(tool_input: dict | None, *, cwd: Path | str = ".") -> str:
    """Build a Claude Code PostToolUse stdin envelope."""
    return json.dumps(
        {
            "session_id": "test",
            "transcript_path": "/dev/null",
            "cwd": str(cwd),
            "permission_mode": "default",
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": tool_input or {},
            "tool_result": {},
        }
    )


# ----------------------------------------------------------------------
# Path-pattern matching
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path, expected",
    [
        # tripwire artifacts
        ("sessions/foo/session.yaml", True),
        ("sessions/foo/pm-response.yaml", True),
        ("sessions/foo/developer.md", True),
        ("sessions/foo/verified.md", True),
        ("sessions/foo/self-review.md", True),
        ("sessions/foo/decisions.md", True),
        ("issues/KUI-1/issue.yaml", True),
        ("nodes/user-model.yaml", True),
        ("graph/nodes/user-model.yaml", True),
        ("project.yaml", True),
        ("graph/index.yaml", True),
        # not tripwire artifacts — must skip silently
        ("src/tripwire/cli/init.py", False),
        ("README.md", False),
        ("docs/some-doc.md", False),
        ("sessions/foo/scratch.md", False),  # not in the allowlist
        ("issues/KUI-1/notes.md", False),
        ("plans/some-plan.md", False),
    ],
)
def test_is_tripwire_artifact(rel_path: str, expected: bool) -> None:
    from tripwire.cli.hooks import _is_tripwire_artifact

    assert _is_tripwire_artifact(rel_path) is expected


# ----------------------------------------------------------------------
# Project-root walk-up
# ----------------------------------------------------------------------


def test_finds_project_root_from_nested_path(tmp_path: Path) -> None:
    from tripwire.cli.hooks import _find_project_root

    _write_minimal_project(tmp_path)
    nested = tmp_path / "sessions" / "abc"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "session.yaml").write_text("---\n", encoding="utf-8")

    assert _find_project_root(nested / "session.yaml") == tmp_path.resolve()


def test_no_project_root_returns_none(tmp_path: Path) -> None:
    from tripwire.cli.hooks import _find_project_root

    no_proj = tmp_path / "loose-dir"
    no_proj.mkdir()
    f = no_proj / "thing.yaml"
    f.write_text("", encoding="utf-8")

    assert _find_project_root(f) is None


# ----------------------------------------------------------------------
# CLI behaviour
# ----------------------------------------------------------------------


def test_hook_skips_silently_for_non_tripwire_path(tmp_path: Path) -> None:
    """Editing a non-tripwire file → exit 0, no stdout."""
    runner = CliRunner()
    payload = _hook_input(
        {"file_path": str(tmp_path / "src" / "main.py")}, cwd=tmp_path
    )
    result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout == ""


def test_hook_skips_silently_with_no_project_root(tmp_path: Path) -> None:
    """No project.yaml above the edited file → exit 0 silent."""
    runner = CliRunner()
    f = tmp_path / "sessions" / "foo" / "session.yaml"
    f.parent.mkdir(parents=True)
    f.write_text("---\n", encoding="utf-8")

    payload = _hook_input({"file_path": str(f)}, cwd=tmp_path)
    result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout == ""


def test_hook_skips_silently_for_malformed_stdin() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "validate-on-edit"], input="not json {{")

    assert result.exit_code == 0
    assert result.stdout == ""


def test_hook_skips_silently_for_missing_file_path() -> None:
    """Stdin valid but missing tool_input → exit 0 silent."""
    runner = CliRunner()
    payload = json.dumps({"hook_event_name": "PostToolUse", "tool_input": {}})
    result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout == ""


def test_hook_passes_silently_on_clean_validate(tmp_path: Path) -> None:
    """Editing a session.yaml in a clean project → exit 0, stdout empty."""
    _write_minimal_project(tmp_path)
    runner = CliRunner()
    sess_dir = tmp_path / "sessions" / "ok"
    sess_dir.mkdir(parents=True)
    sess_path = sess_dir / "session.yaml"
    sess_path.write_text("---\n", encoding="utf-8")

    payload = _hook_input({"file_path": str(sess_path)}, cwd=tmp_path)
    # Patch validate_project to return a clean report.
    with patch("tripwire.cli.hooks.validate_project") as mock_validate:
        from tripwire.core.validator import ValidationReport

        mock_validate.return_value = ValidationReport(
            errors=[], warnings=[], fixed=[], exit_code=0
        )
        result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_hook_emits_block_json_on_validate_failure(tmp_path: Path) -> None:
    """Failing validate → stdout has decision:'block' + reason; exit 0."""
    _write_minimal_project(tmp_path)
    runner = CliRunner()
    sess_dir = tmp_path / "sessions" / "fail"
    sess_dir.mkdir(parents=True)
    sess_path = sess_dir / "session.yaml"
    sess_path.write_text("---\n", encoding="utf-8")

    payload = _hook_input({"file_path": str(sess_path)}, cwd=tmp_path)
    with patch("tripwire.cli.hooks.validate_project") as mock_validate:
        from tripwire.core.validator import CheckResult, ValidationReport

        finding = CheckResult(
            code="status/invalid_enum",
            severity="error",
            file="sessions/fail/session.yaml",
            field="status",
            message="status 'nonsense' is not in SessionStatus",
        )
        mock_validate.return_value = ValidationReport(
            errors=[finding], warnings=[], fixed=[], exit_code=2
        )
        result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout.strip(), "expected block JSON on stdout"
    body = json.loads(result.stdout)
    assert body["decision"] == "block"
    assert "reason" in body
    assert "status/invalid_enum" in body["reason"]


def test_hook_handles_notebook_path(tmp_path: Path) -> None:
    """`tool_input.notebook_path` is treated like `file_path`."""
    _write_minimal_project(tmp_path)
    runner = CliRunner()
    sess_dir = tmp_path / "sessions" / "nb"
    sess_dir.mkdir(parents=True)
    sess_path = sess_dir / "session.yaml"
    sess_path.write_text("---\n", encoding="utf-8")

    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_input": {"notebook_path": str(sess_path)},
            "cwd": str(tmp_path),
        }
    )
    with patch("tripwire.cli.hooks.validate_project") as mock_validate:
        from tripwire.core.validator import ValidationReport

        mock_validate.return_value = ValidationReport(
            errors=[], warnings=[], fixed=[], exit_code=0
        )
        result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)
    assert result.exit_code == 0


def test_hook_swallows_internal_exception(tmp_path: Path) -> None:
    """validate_project raising an unexpected exception → exit 0 silent."""
    _write_minimal_project(tmp_path)
    runner = CliRunner()
    sess_dir = tmp_path / "sessions" / "boom"
    sess_dir.mkdir(parents=True)
    sess_path = sess_dir / "session.yaml"
    sess_path.write_text("---\n", encoding="utf-8")

    payload = _hook_input({"file_path": str(sess_path)}, cwd=tmp_path)
    with patch("tripwire.cli.hooks.validate_project") as mock_validate:
        mock_validate.side_effect = RuntimeError("boom")
        result = runner.invoke(cli, ["hook", "validate-on-edit"], input=payload)

    assert result.exit_code == 0
    assert result.stdout == ""


def test_hook_timeout_exits_silent(tmp_path: Path) -> None:
    """Validation that takes >timeout seconds → exit 0 silent."""
    _write_minimal_project(tmp_path)
    runner = CliRunner()
    sess_dir = tmp_path / "sessions" / "slow"
    sess_dir.mkdir(parents=True)
    sess_path = sess_dir / "session.yaml"
    sess_path.write_text("---\n", encoding="utf-8")

    import time

    def _slow_validate(*args, **kwargs):
        time.sleep(2)  # exceeds the test-mode timeout below
        from tripwire.core.validator import ValidationReport

        return ValidationReport(errors=[], warnings=[], fixed=[], exit_code=0)

    payload = _hook_input({"file_path": str(sess_path)}, cwd=tmp_path)
    # We pass timeout=1 second so the test runs fast.
    with patch("tripwire.cli.hooks.validate_project", _slow_validate):
        result = runner.invoke(
            cli,
            ["hook", "validate-on-edit", "--timeout-seconds", "1"],
            input=payload,
        )

    assert result.exit_code == 0
    assert result.stdout == ""
