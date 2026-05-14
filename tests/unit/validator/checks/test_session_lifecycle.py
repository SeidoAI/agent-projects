"""v0.13 — session-lifecycle tripwires (promoted from side-effects).

One happy-path + one failure-finding test per validator:

- ``check_pr_merged_for_session``       → ``session/pr_not_merged``
- ``check_pr_review_approved``          → ``session/review_not_approved``
- ``check_session_has_developer_md``    → ``session/developer_md_missing``
- ``check_session_has_verified_md``     → ``session/verified_md_missing``

The PR-merged tests monkeypatch ``_pr_merged_for_branch`` to avoid
shelling out to ``gh`` from the test process.
"""

from __future__ import annotations

import json
from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.checks import session_lifecycle as sl
from tripwire.core.validator.checks.session_lifecycle import (
    check_pr_merged_for_session,
    check_pr_review_approved,
    check_session_has_developer_md,
    check_session_has_verified_md,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_session_with_worktree(
    save_test_session,
    project_dir: Path,
    sid: str,
    *,
    status: str,
    branch: str = "feat/test",
    issues: list[str] | None = None,
) -> None:
    """Save a session with one worktree record so the PR-merged check
    has something to iterate. ``worktree_path`` points to the session
    dir — the real path doesn't matter because we monkeypatch the gh
    shell-out."""
    save_test_session(
        project_dir,
        sid,
        status=status,
        issues=issues or [],
        runtime_state={
            "worktrees": [
                {
                    "repo": "SeidoAI/tmp",
                    "clone_path": str(project_dir),
                    "worktree_path": str(project_dir),
                    "branch": branch,
                }
            ],
        },
    )


def _write_review_json(project_dir: Path, sid: str, *, exit_code: int) -> None:
    sdir = project_dir / "instances" / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "review.json").write_text(
        json.dumps({"exit_code": exit_code, "verdict": "approved"}),
        encoding="utf-8",
    )


def _save_issue(save_test_issue, project_dir: Path, key: str, *, status: str) -> None:
    save_test_issue(project_dir, key, status=status)


# ---------------------------------------------------------------------------
# v_pr_merged_for_session
# ---------------------------------------------------------------------------


class TestPrMergedForSession:
    def test_happy_path_all_merged(
        self,
        tmp_path_project,
        save_test_session,
        monkeypatch,
    ):
        _seed_session_with_worktree(
            save_test_session, tmp_path_project, "s1", status="verified"
        )
        monkeypatch.setattr(sl, "_pr_merged_for_branch", lambda _wt, _br: True)
        ctx = load_context(tmp_path_project)
        assert check_pr_merged_for_session(ctx) == []

    def test_unmerged_branch_fires(
        self,
        tmp_path_project,
        save_test_session,
        monkeypatch,
    ):
        _seed_session_with_worktree(
            save_test_session, tmp_path_project, "s1", status="verified"
        )
        monkeypatch.setattr(sl, "_pr_merged_for_branch", lambda _wt, _br: False)
        ctx = load_context(tmp_path_project)
        results = check_pr_merged_for_session(ctx)
        assert any(r.code == "session/pr_not_merged" for r in results), (
            f"expected session/pr_not_merged, got {[r.code for r in results]}"
        )

    def test_pre_verified_skips(
        self,
        tmp_path_project,
        save_test_session,
        monkeypatch,
    ):
        """Sessions before `verified` are off-gate — nothing should fire
        even when no PR is merged. Closes the trap shape where validators
        accidentally bite mid-flight sessions."""
        _seed_session_with_worktree(
            save_test_session, tmp_path_project, "s1", status="executing"
        )
        monkeypatch.setattr(sl, "_pr_merged_for_branch", lambda _wt, _br: False)
        ctx = load_context(tmp_path_project)
        assert check_pr_merged_for_session(ctx) == []


# ---------------------------------------------------------------------------
# v_pr_review_approved
# ---------------------------------------------------------------------------


class TestPrReviewApproved:
    def test_happy_path_exit_code_zero(
        self,
        tmp_path_project,
        save_test_session,
    ):
        save_test_session(tmp_path_project, "s1", status="verified")
        _write_review_json(tmp_path_project, "s1", exit_code=0)
        ctx = load_context(tmp_path_project)
        assert check_pr_review_approved(ctx) == []

    def test_high_exit_code_fires(
        self,
        tmp_path_project,
        save_test_session,
    ):
        save_test_session(tmp_path_project, "s1", status="verified")
        _write_review_json(tmp_path_project, "s1", exit_code=2)
        ctx = load_context(tmp_path_project)
        results = check_pr_review_approved(ctx)
        assert any(r.code == "session/review_not_approved" for r in results), (
            f"expected session/review_not_approved, got {[r.code for r in results]}"
        )

    def test_missing_review_json_fires(
        self,
        tmp_path_project,
        save_test_session,
    ):
        save_test_session(tmp_path_project, "s1", status="verified")
        ctx = load_context(tmp_path_project)
        results = check_pr_review_approved(ctx)
        assert any(r.code == "session/review_not_approved" for r in results)


# ---------------------------------------------------------------------------
# v_session_has_developer_md
# ---------------------------------------------------------------------------


class TestSessionHasDeveloperMd:
    def test_happy_path_artifact_present(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="in_review")
        save_test_session(
            tmp_path_project, "s1", status="in_review", issues=["TMP-1"]
        )
        (tmp_path_project / "instances" / "issues" / "TMP-1" / "docs" / "developer.md").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path_project / "instances" / "issues" / "TMP-1" / "docs" / "developer.md").write_text(
            "## Developer notes\n\nReady for review.\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        assert check_session_has_developer_md(ctx) == []

    def test_missing_artifact_fires(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="in_review")
        save_test_session(
            tmp_path_project, "s1", status="in_review", issues=["TMP-1"]
        )
        # No developer.md written on purpose.
        ctx = load_context(tmp_path_project)
        results = check_session_has_developer_md(ctx)
        assert any(r.code == "session/developer_md_missing" for r in results), (
            f"expected session/developer_md_missing, got {[r.code for r in results]}"
        )


# ---------------------------------------------------------------------------
# v_session_has_verified_md
# ---------------------------------------------------------------------------


class TestSessionHasVerifiedMd:
    def test_happy_path_artifact_present(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="verified")
        save_test_session(
            tmp_path_project, "s1", status="verified", issues=["TMP-1"]
        )
        issue_docs_dir = (
            tmp_path_project / "instances" / "issues" / "TMP-1" / "docs"
        )
        issue_docs_dir.mkdir(parents=True, exist_ok=True)
        (issue_docs_dir / "developer.md").write_text("dev notes\n", encoding="utf-8")
        (issue_docs_dir / "verified.md").write_text(
            "verified notes\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        assert check_session_has_verified_md(ctx) == []

    def test_missing_artifact_fires(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="verified")
        save_test_session(
            tmp_path_project, "s1", status="verified", issues=["TMP-1"]
        )
        # developer.md present (so the developer-md check doesn't noise),
        # but verified.md intentionally missing.
        (tmp_path_project / "instances" / "issues" / "TMP-1" / "docs" / "developer.md").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path_project / "instances" / "issues" / "TMP-1" / "docs" / "developer.md").write_text(
            "dev notes\n", encoding="utf-8"
        )
        ctx = load_context(tmp_path_project)
        results = check_session_has_verified_md(ctx)
        assert any(r.code == "session/verified_md_missing" for r in results), (
            f"expected session/verified_md_missing, got {[r.code for r in results]}"
        )
