"""Pattern aggregation across pm-review verdicts (KUI-151).

Reads ``pm_review.completed`` events from the events log, aggregates
the per-check failure counts across sessions, and surfaces recurring
patterns. Read-only — never mutates the events log or the artifacts.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_with_events(tmp_path: Path) -> Path:
    """Build a project with N pm_review.completed events."""
    from tripwire.core.events.log import emit_event

    pd = tmp_path
    (pd / "events").mkdir()
    # 4 of 5 sessions failed `schema`; 3 of 5 failed `refs`.
    sessions = [
        ("sess-1", "request_changes", ["schema", "refs", "freshness"]),
        ("sess-2", "request_changes", ["schema", "refs"]),
        ("sess-3", "request_changes", ["schema"]),
        ("sess-4", "request_changes", ["schema", "refs"]),
        ("sess-5", "auto-merge", []),
    ]
    for sid, outcome, failed in sessions:
        emit_event(
            pd,
            workflow="pm-review",
            instance=sid,
            status="review",
            event="pm_review.completed",
            details={
                "outcome": outcome,
                "failed_checks": failed,
                "passed_checks": [],
            },
        )
    return pd


def test_aggregate_returns_per_check_failure_counts(project_with_events):
    from tripwire.core.pm_review.aggregate import aggregate_patterns

    result = aggregate_patterns(project_with_events)

    assert result.total_reviews == 5
    counts = {p.check: p.fail_count for p in result.patterns}
    assert counts.get("schema") == 4
    assert counts.get("refs") == 3
    assert counts.get("freshness") == 1
    # Outcome breakdown
    assert result.outcome_counts.get("request_changes") == 4
    assert result.outcome_counts.get("auto-merge") == 1


def test_aggregate_filters_by_check_threshold(project_with_events):
    """``min_fail_count`` filters out one-off failures."""
    from tripwire.core.pm_review.aggregate import aggregate_patterns

    result = aggregate_patterns(project_with_events, min_fail_count=3)
    names = {p.check for p in result.patterns}
    # `freshness` (1 fail) drops out, `schema` and `refs` stay.
    assert "schema" in names
    assert "refs" in names
    assert "freshness" not in names


def test_aggregate_handles_empty_events(tmp_path):
    """A project with no events log yields zero reviews."""
    from tripwire.core.pm_review.aggregate import aggregate_patterns

    result = aggregate_patterns(tmp_path)
    assert result.total_reviews == 0
    assert result.patterns == []
