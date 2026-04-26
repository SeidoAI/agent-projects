"""``tripwire session analyze-routing`` (KUI-96 §E4).

Reads ``sessions/.routing_telemetry.jsonl`` and surfaces $/merged-PR
ratio + sample size per (provider, model, effort, task_kind) route.
Manual interpretation today — auto-tuning is v0.8 scope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.routing_telemetry import (
    TelemetryRow,
    append_telemetry_row,
)


def _row(**overrides) -> TelemetryRow:
    base = {
        "sid": "s",
        "task_kind": "agentic_loop",
        "provider": "claude",
        "model": "opus",
        "effort": "xhigh",
        "merged": True,
        "cost_usd": 10.0,
        "duration_min": 20,
        "re_engages": 0,
        "ci_failures": 0,
    }
    base.update(overrides)
    return TelemetryRow(**base)


def test_analyze_routing_groups_by_route(tmp_path_project: Path) -> None:
    """Rows with the same route are grouped; cost is summed; n is counted."""
    for sid, cost in [("a", 50.0), ("b", 30.0), ("c", 20.0)]:
        append_telemetry_row(
            tmp_path_project, _row(sid=sid, cost_usd=cost, model="opus")
        )
    append_telemetry_row(
        tmp_path_project, _row(sid="d", cost_usd=5.0, model="sonnet", effort="medium")
    )

    runner = CliRunner(env={"COLUMNS": "200"})
    result = runner.invoke(
        session_cmd,
        [
            "analyze-routing",
            "--project-dir",
            str(tmp_path_project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    by_route = {
        (r["provider"], r["model"], r["effort"], r["task_kind"]): r
        for r in payload["routes"]
    }
    opus = by_route[("claude", "opus", "xhigh", "agentic_loop")]
    assert opus["n"] == 3
    assert opus["merged"] == 3
    assert opus["total_cost_usd"] == pytest.approx(100.0)
    # Rounded to 4 decimals on disk; tolerate the rounding here.
    assert opus["cost_per_merged_pr"] == pytest.approx(100.0 / 3, abs=1e-3)

    sonnet = by_route[("claude", "sonnet", "medium", "agentic_loop")]
    assert sonnet["n"] == 1
    assert sonnet["cost_per_merged_pr"] == 5.0


def test_analyze_routing_handles_zero_merged(tmp_path_project: Path) -> None:
    """A route with no merged sessions reports infinite ratio as ``None``."""
    append_telemetry_row(
        tmp_path_project,
        _row(sid="x", merged=False, cost_usd=10.0),
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "analyze-routing",
            "--project-dir",
            str(tmp_path_project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    route = payload["routes"][0]
    assert route["merged"] == 0
    assert route["cost_per_merged_pr"] is None


def test_analyze_routing_no_data(tmp_path_project: Path) -> None:
    """No telemetry yet: command exits cleanly with an empty report."""
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        [
            "analyze-routing",
            "--project-dir",
            str(tmp_path_project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["routes"] == []
    assert payload["total_sessions"] == 0


def test_analyze_routing_table_format_renders(tmp_path_project: Path) -> None:
    """Default table format renders without erroring."""
    append_telemetry_row(tmp_path_project, _row(sid="x", cost_usd=10.0))
    runner = CliRunner(env={"COLUMNS": "200"})
    result = runner.invoke(
        session_cmd,
        ["analyze-routing", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "opus" in result.output
    assert "agentic_loop" in result.output
