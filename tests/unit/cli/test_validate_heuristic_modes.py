"""`tripwire validate` heuristic-mode flags (C6).

Each flag toggles the heuristic-finding pipeline: ``surface`` (default),
``quiet`` (suppress acked), ``none`` (skip entirely), ``as_tripwires``
(promote to error, ignore markers).

These tests use the in-process click ``CliRunner`` plus a stub
``validate_project`` to assert flag plumbing without spinning up a real
project. The actual filtering behaviour is exercised by
``tests/unit/validator/test_apply_heuristic_mode.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.validate import validate_cmd
from tripwire.core.validator import ValidationReport


def _stub_validate_project(captured: dict):
    def _stub(project_dir: Path, **kwargs):
        captured["project_dir"] = project_dir
        captured.update(kwargs)
        return ValidationReport(exit_code=0)

    return _stub


def test_default_uses_surface_mode():
    captured: dict = {}
    runner = CliRunner()
    with patch(
        "tripwire.cli.validate.validate_project",
        side_effect=_stub_validate_project(captured),
    ):
        result = runner.invoke(validate_cmd, ["--project-dir", "."])
    assert result.exit_code == 0, result.output
    assert captured["heuristic_mode"] == "surface"


def test_quiet_heuristics_flag_maps_to_quiet_mode():
    captured: dict = {}
    runner = CliRunner()
    with patch(
        "tripwire.cli.validate.validate_project",
        side_effect=_stub_validate_project(captured),
    ):
        result = runner.invoke(validate_cmd, ["--quiet-heuristics", "--project-dir", "."])
    assert result.exit_code == 0, result.output
    assert captured["heuristic_mode"] == "quiet"


def test_no_heuristics_flag_maps_to_none_mode():
    captured: dict = {}
    runner = CliRunner()
    with patch(
        "tripwire.cli.validate.validate_project",
        side_effect=_stub_validate_project(captured),
    ):
        result = runner.invoke(validate_cmd, ["--no-heuristics", "--project-dir", "."])
    assert result.exit_code == 0, result.output
    assert captured["heuristic_mode"] == "none"


def test_heuristics_as_tripwires_flag_maps_to_as_tripwires_mode():
    captured: dict = {}
    runner = CliRunner()
    with patch(
        "tripwire.cli.validate.validate_project",
        side_effect=_stub_validate_project(captured),
    ):
        result = runner.invoke(
            validate_cmd, ["--heuristics-as-tripwires", "--project-dir", "."]
        )
    assert result.exit_code == 0, result.output
    assert captured["heuristic_mode"] == "as_tripwires"


def test_heuristic_flags_are_mutually_exclusive():
    runner = CliRunner()
    with patch("tripwire.cli.validate.validate_project") as mock:
        result = runner.invoke(
            validate_cmd,
            ["--quiet-heuristics", "--no-heuristics", "--project-dir", "."],
        )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output
    mock.assert_not_called()


def test_strict_flag_no_longer_exists():
    """Stage-1 hard removal: --strict is gone (was: strict-by-default).

    The CLI must reject the flag even though the underlying
    ``validate_project`` still accepts ``strict=True`` programmatically.
    """
    runner = CliRunner()
    result = runner.invoke(validate_cmd, ["--strict", "--project-dir", "."])
    assert result.exit_code != 0
    assert "--strict" in result.output or "no such option" in result.output.lower()
