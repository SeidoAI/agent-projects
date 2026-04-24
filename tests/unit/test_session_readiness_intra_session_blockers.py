"""Tests for I4 — same-session blockers don't fail readiness.

v0.7.2 readiness check treated every blocker on every session-issue
as a prerequisite, including blockers that were themselves in the
same session (and would be completed in the same spawn). Example:
session with KUI-68 and KUI-69, where KUI-69 has
`blocked_by: [KUI-68]`, falsely failed readiness.

Fix at src/tripwire/core/session_readiness.py: skip blockers whose
key is in session.issues.
"""

from __future__ import annotations


def _blocker_items(report):
    return [i for i in report.items if i.label.startswith("blocker:")]


class TestIntraSessionBlockersSkipped:
    def test_same_session_blocker_does_not_fail_readiness(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """A and B both in session.issues; B blocked_by A. Readiness
        must NOT report A as a blocker — it'll be done in this spawn."""
        from tripwire.core.session_readiness import check_readiness

        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_issue(
            tmp_path_project, "TMP-2", status="backlog", blocked_by=["TMP-1"]
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            issues=["TMP-1", "TMP-2"],
        )

        report = check_readiness(tmp_path_project, "s1")

        blockers = _blocker_items(report)
        assert blockers == [], (
            "Same-session blockers should be filtered out; got: "
            + ", ".join(b.label for b in blockers)
        )

    def test_cross_session_blocker_still_fails(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """A is NOT in session.issues; B lists A in blocked_by. Readiness
        MUST still report A as a blocker — this is the existing
        correctness guarantee. Regression test."""
        from tripwire.core.session_readiness import check_readiness

        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_issue(
            tmp_path_project, "TMP-2", status="backlog", blocked_by=["TMP-1"]
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            issues=["TMP-2"],  # NOTE: TMP-1 not in session
        )

        report = check_readiness(tmp_path_project, "s1")

        blockers = _blocker_items(report)
        assert len(blockers) == 1
        assert "TMP-1" in blockers[0].label
        assert blockers[0].severity == "error"

    def test_same_session_done_blocker_still_no_item(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """Control — A is in session.issues AND status=done. No blocker
        item either way (filter applies before status check)."""
        from tripwire.core.session_readiness import check_readiness

        save_test_issue(tmp_path_project, "TMP-1", status="done")
        save_test_issue(
            tmp_path_project, "TMP-2", status="backlog", blocked_by=["TMP-1"]
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            issues=["TMP-1", "TMP-2"],
        )

        report = check_readiness(tmp_path_project, "s1")

        assert _blocker_items(report) == []

    def test_mixed_cross_and_intra_session_blockers(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        """B is blocked by both A (in-session) and X (out-of-session,
        backlog). Only X should show up as a blocker."""
        from tripwire.core.session_readiness import check_readiness

        save_test_issue(tmp_path_project, "TMP-1", status="backlog")
        save_test_issue(tmp_path_project, "TMP-99", status="backlog")
        save_test_issue(
            tmp_path_project,
            "TMP-2",
            status="backlog",
            blocked_by=["TMP-1", "TMP-99"],
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            issues=["TMP-1", "TMP-2"],
        )

        report = check_readiness(tmp_path_project, "s1")
        blockers = _blocker_items(report)

        assert len(blockers) == 1
        assert "TMP-99" in blockers[0].label
