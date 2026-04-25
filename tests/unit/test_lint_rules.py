"""Per-rule tests for tripwire lint project-only rules (v0.6a)."""

from datetime import datetime, timedelta, timezone

from tripwire.core import lint_rules  # noqa: F401 — registers rules
from tripwire.core.linter import Linter


class TestGapAnalysisRowDensity:
    def test_flags_low_density(self, save_test_issue, tmp_path_project):
        """Gap analysis with fewer rows than issue count triggers warning."""
        # Write a thin gap-analysis table (1 data row).
        (tmp_path_project / "docs" / "gap-analysis.md").write_text(
            "| Deliverable | Gap |\n|---|---|\n| A | x |\n",
            encoding="utf-8",
        )
        for i in range(1, 10):
            save_test_issue(
                tmp_path_project, key=f"TMP-{i}", kind="feat", title=f"T{i}"
            )
        linter = Linter(project_dir=tmp_path_project)
        findings = list(linter.run_stage("scoping"))
        assert any(f.code == "lint/gap_analysis_row_density" for f in findings)

    def test_no_finding_when_gap_doc_absent(self, save_test_issue, tmp_path_project):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="X")
        linter = Linter(project_dir=tmp_path_project)
        findings = list(linter.run_stage("scoping"))
        assert not any(f.code == "lint/gap_analysis_row_density" for f in findings)


class TestSessionStale:
    def test_flags_long_in_executing(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="Setup")
        save_test_session(
            tmp_path_project,
            session_id="session-setup",
            issues=["TMP-1"],
            status="executing",
            updated_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
        )
        linter = Linter(project_dir=tmp_path_project, session_id="session-setup")
        findings = list(linter.run_stage("session"))
        assert any(f.code == "lint/session_stale" for f in findings)

    def test_no_finding_when_recent(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="Setup")
        save_test_session(
            tmp_path_project,
            session_id="session-setup",
            issues=["TMP-1"],
            status="executing",
            updated_at=datetime.now(tz=timezone.utc),
        )
        linter = Linter(project_dir=tmp_path_project, session_id="session-setup")
        findings = list(linter.run_stage("session"))
        assert not any(f.code == "lint/session_stale" for f in findings)


class TestBranchConvention:
    def test_flags_invalid_branch(
        self, save_test_issue, save_test_session, tmp_path_project
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="X")
        save_test_session(tmp_path_project, session_id="session-x", issues=["TMP-1"])
        sess = tmp_path_project / "sessions" / "session-x"
        (sess / "handoff.yaml").write_text(
            """---
uuid: 11111111-1111-1111-1111-111111111111
session_id: session-x
handoff_at: 2026-04-15T00:00:00Z
handed_off_by: pm
branch: not-valid-branch
---
""",
            encoding="utf-8",
        )
        linter = Linter(project_dir=tmp_path_project, session_id="session-x")
        findings = list(linter.run_stage("handoff"))
        assert any(f.code == "lint/branch_convention" for f in findings)

    def test_passes_valid_branch(
        self,
        save_test_issue,
        save_test_session,
        tmp_path_project,
        write_handoff_yaml,
    ):
        save_test_issue(tmp_path_project, key="TMP-1", kind="feat", title="X")
        save_test_session(tmp_path_project, session_id="session-x", issues=["TMP-1"])
        write_handoff_yaml(tmp_path_project, "session-x", branch="feat/valid-slug")
        linter = Linter(project_dir=tmp_path_project, session_id="session-x")
        findings = list(linter.run_stage("handoff"))
        assert not any(f.code == "lint/branch_convention" for f in findings)


class TestUnpushedPromotions:
    def test_unpushed_promotions_no_op_in_v0_6a(self, save_test_node, tmp_path_project):
        """Without v0.6b's origin/scope fields, the rule defaults to no-op
        (local/local state → not a promotion candidate)."""
        save_test_node(tmp_path_project, node_id="local-concept")
        linter = Linter(project_dir=tmp_path_project)
        findings = list(linter.run_stage("scoping"))
        assert not any(f.code == "lint/unpushed_promotion_candidates" for f in findings)
