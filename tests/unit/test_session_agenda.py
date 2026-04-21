"""Session agenda DAG computation and recommendations."""

import pytest

from tripwire.core.session_agenda import (
    CycleDetectedError,
    build_agenda,
)


def _session(id: str, status: str = "planned", blocked_by: list[str] | None = None):
    return {"id": id, "status": status, "blocked_by_sessions": blocked_by or []}


class TestBuildAgenda:
    def test_no_sessions(self):
        report = build_agenda([])
        assert report.launchable == []
        assert report.blocked == []

    def test_single_unblocked_session(self):
        report = build_agenda([_session("s1")])
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s1"

    def test_two_independent_sessions(self):
        report = build_agenda([_session("s1"), _session("s2")])
        assert len(report.launchable) == 2

    def test_blocked_session(self):
        report = build_agenda(
            [
                _session("s1"),
                _session("s2", blocked_by=["s1"]),
            ]
        )
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s1"
        assert len(report.blocked) == 1
        assert report.blocked[0].id == "s2"

    def test_completed_blocker_unblocks(self):
        report = build_agenda(
            [
                _session("s1", status="completed"),
                _session("s2", blocked_by=["s1"]),
            ]
        )
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s2"

    def test_critical_path_linear(self):
        report = build_agenda(
            [
                _session("s1"),
                _session("s2", blocked_by=["s1"]),
                _session("s3", blocked_by=["s2"]),
            ]
        )
        assert report.critical_path == ["s1", "s2", "s3"]

    def test_critical_path_picks_longest(self):
        report = build_agenda(
            [
                _session("s1"),
                _session("s2"),
                _session("s3", blocked_by=["s1"]),
                _session("s4", blocked_by=["s3"]),
            ]
        )
        assert report.critical_path == ["s1", "s3", "s4"]

    def test_cycle_detected(self):
        with pytest.raises(CycleDetectedError) as exc_info:
            build_agenda(
                [
                    _session("s1", blocked_by=["s2"]),
                    _session("s2", blocked_by=["s1"]),
                ]
            )
        assert "s1" in str(exc_info.value) or "s2" in str(exc_info.value)

    def test_orphan_blocker_treated_as_unblocked(self):
        report = build_agenda(
            [
                _session("s1", blocked_by=["nonexistent"]),
            ]
        )
        assert len(report.launchable) == 1
        assert len(report.warnings) > 0

    def test_recommendations_by_blast_radius(self):
        report = build_agenda(
            [
                _session("s1"),
                _session("s2"),
                _session("s3", blocked_by=["s1"]),
                _session("s4", blocked_by=["s1"]),
            ]
        )
        assert report.recommendations[0].session_id == "s1"

    def test_totals(self):
        report = build_agenda(
            [
                _session("s1", status="completed"),
                _session("s2", status="executing"),
                _session("s3"),
                _session("s4", blocked_by=["s3"]),
            ]
        )
        assert report.totals["completed"] == 1
        assert report.totals["executing"] == 1
        assert report.totals["planned"] == 2

    def test_executing_not_launchable(self):
        report = build_agenda([_session("s1", status="executing")])
        assert len(report.launchable) == 0
        assert len(report.in_flight) == 1

    def test_all_completed(self):
        report = build_agenda(
            [
                _session("s1", status="completed"),
                _session("s2", status="completed"),
            ]
        )
        assert report.all_completed is True
