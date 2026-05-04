"""`tripwire heuristic` CLI surface."""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from tripwire._internal.heuristics import write_marker
from tripwire._internal.heuristics._acks import ACK_DIR_REL, MarkerKey
from tripwire.cli.heuristic import heuristic_cmd


def test_list_with_no_markers(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(heuristic_cmd, ["list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "v_stale_concept" in result.output
    assert "acked=0" in result.output


def test_list_reports_marker_counts(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u2", "h2"))

    runner = CliRunner()
    result = runner.invoke(heuristic_cmd, ["list", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    line = next(
        ln for ln in result.output.splitlines() if ln.startswith("v_mega_issue")
    )
    assert "acked=2" in line


def test_reset_unknown_id_is_usage_error(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        heuristic_cmd, ["reset", "v_no_such_heuristic", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "unknown heuristic" in result.output


def test_reset_without_id_or_all_flag_is_usage_error(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(heuristic_cmd, ["reset", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "--all" in result.output


def test_reset_clears_markers(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u2", "h2"))

    runner = CliRunner()
    result = runner.invoke(
        heuristic_cmd, ["reset", "v_mega_issue", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "removed 2 marker(s)" in result.output
    assert not (tmp_path / ACK_DIR_REL / "v_mega_issue").exists()


def test_reset_all_clears_every_marker(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_stale_concept", "u3", "h3"))

    runner = CliRunner()
    result = runner.invoke(
        heuristic_cmd, ["reset", "--all", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "removed 2 marker(s)" in result.output


def test_gc_runs_against_real_project(tmp_path: Path):
    """`tripwire heuristic gc` walks the real validator context loader.

    Use ``tripwire init`` to scaffold a minimal valid project so the
    loader has real entities to enumerate. The test only asserts the
    command succeeds and reports a count — exact GC math is covered by
    ``test_acks.test_gc_markers_removes_only_dead_entities``.
    """
    repo_root = Path(__file__).resolve().parents[3]
    proj = tmp_path / "p"
    init = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root),
            "tripwire",
            "init",
            "--name",
            "p",
            "--key-prefix",
            "P",
            "--non-interactive",
            "--no-remote",
            str(proj),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stdout + init.stderr

    write_marker(proj, MarkerKey("v_mega_issue", "deleted-entity", "h1"))

    runner = CliRunner()
    result = runner.invoke(heuristic_cmd, ["gc", "--project-dir", str(proj)])
    assert result.exit_code == 0, result.output
    assert "removed 1 stale marker(s)" in result.output
