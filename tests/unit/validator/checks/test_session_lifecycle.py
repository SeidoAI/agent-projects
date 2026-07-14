"""v0.13/v0.14 — session-lifecycle tripwires.

One happy-path + one failure-finding test per validator:

- ``check_member_issues_at_or_past_in_review`` → ``session/member_issue_not_swept`` (v0.14.0)
- ``check_pr_merged_for_session``              → ``session/pr_not_merged``
- ``check_pr_review_approved``                 → ``session/review_not_approved``
- ``check_session_has_developer_md``           → ``session/developer_md_missing``
- ``check_session_has_verified_md``            → ``session/verified_md_missing``

The PR-merged tests monkeypatch ``_pr_merged_for_branch`` to avoid
shelling out to ``gh`` from the test process.
"""

from __future__ import annotations

import json
from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.checks.session import pr_merged_for_session as sl
from tripwire.core.validator.checks.session.member_issues_at_or_past_in_review import (
    check_member_issues_at_or_past_in_review,
)
from tripwire.core.validator.checks.session.pr_merged_for_session import (
    check_pr_merged_for_session,
)
from tripwire.core.validator.checks.session.pr_review_approved import (
    check_pr_review_approved,
)
from tripwire.core.validator.checks.session.session_has_developer_md import (
    check_session_has_developer_md,
)
from tripwire.core.validator.checks.session.session_has_verified_md import (
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
# v_member_issues_at_or_past_in_review (v0.14.0)
# ---------------------------------------------------------------------------


class TestMemberIssuesAtOrPastInReview:
    def test_happy_path_all_member_issues_at_in_review(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="in_review")
        _save_issue(save_test_issue, tmp_path_project, "TMP-2", status="verified")
        save_test_session(
            tmp_path_project,
            "s1",
            status="in_review",
            issues=["TMP-1", "TMP-2"],
        )
        ctx = load_context(tmp_path_project)
        assert check_member_issues_at_or_past_in_review(ctx) == []

    def test_unswept_member_issue_fires(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="in_review")
        _save_issue(save_test_issue, tmp_path_project, "TMP-2", status="queued")
        save_test_session(
            tmp_path_project,
            "s1",
            status="in_review",
            issues=["TMP-1", "TMP-2"],
        )
        ctx = load_context(tmp_path_project)
        results = check_member_issues_at_or_past_in_review(ctx)
        assert any(r.code == "session/member_issue_not_swept" for r in results), (
            f"expected session/member_issue_not_swept, got {[r.code for r in results]}"
        )
        # Only the unswept one (TMP-2) should be named in any finding message.
        swept_messages = [r.message for r in results if "TMP-1" in r.message]
        assert swept_messages == []

    def test_executing_session_does_not_fire(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        # Session still at executing — the backstop only gates once
        # the session has reached in_review. Pre-in_review is the
        # legal sweep window, not a failure window.
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="queued")
        save_test_session(tmp_path_project, "s1", status="executing", issues=["TMP-1"])
        ctx = load_context(tmp_path_project)
        assert check_member_issues_at_or_past_in_review(ctx) == []


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

    def test_completed_session_skips(
        self,
        tmp_path_project,
        save_test_session,
        monkeypatch,
    ):
        """Regression test for v0.13.2 #5.

        A completed session still carries worktree records in
        ``runtime_state.worktrees`` (cleanup doesn't clear them today).
        Before v0.13.2 the gate was ``_session_at_or_past('verified')``
        so completed sessions re-fired the PR-merged check; the worktree
        dirs are gone after completion, so ``subprocess.run(cwd=...)``
        raises ``FileNotFoundError``, surfaced as ``GhError``, treated
        as "not merged" — permanent noise per completed session.

        After: gate is exact ``== "verified"``; completed sessions skip.
        """
        _seed_session_with_worktree(
            save_test_session, tmp_path_project, "s1", status="completed"
        )
        # If the gate were re-broadened, this lambda would force a
        # finding; the tightened gate must skip before reaching it.
        monkeypatch.setattr(sl, "_pr_merged_for_branch", lambda _wt, _br: False)
        ctx = load_context(tmp_path_project)
        assert check_pr_merged_for_session(ctx) == []

    def test_missing_worktree_dir_does_not_fire(
        self,
        tmp_path_project,
        save_test_session,
        monkeypatch,
    ):
        """Defensive check for v0.13.2 #5.

        Even on a verified session, a worktree whose dir has been
        removed should not surface as "not merged" — that's an absent
        prerequisite, not a remote PR state.
        """
        save_test_session(
            tmp_path_project,
            "s2",
            status="verified",
            issues=[],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/tmp",
                        "clone_path": str(tmp_path_project),
                        "worktree_path": str(tmp_path_project / "gone-worktree"),
                        "branch": "feat/missing",
                    }
                ],
            },
        )
        # _pr_merged_for_branch must NOT be called for the missing
        # worktree; if it is, we'd see "not merged" surface.
        called = {"hit": False}

        def _spy(_wt, _br):
            called["hit"] = True
            return False

        monkeypatch.setattr(sl, "_pr_merged_for_branch", _spy)
        ctx = load_context(tmp_path_project)
        results = check_pr_merged_for_session(ctx)
        assert results == [], (
            f"expected no findings for missing worktree, got "
            f"{[r.code for r in results]}"
        )
        assert called["hit"] is False, (
            "_pr_merged_for_branch was called against a missing worktree path"
        )


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
        save_test_session(tmp_path_project, "s1", status="in_review", issues=["TMP-1"])
        (
            tmp_path_project
            / "instances"
            / "issues"
            / "TMP-1"
            / "docs"
            / "developer.md"
        ).parent.mkdir(parents=True, exist_ok=True)
        (
            tmp_path_project
            / "instances"
            / "issues"
            / "TMP-1"
            / "docs"
            / "developer.md"
        ).write_text("## Developer notes\n\nReady for review.\n", encoding="utf-8")
        ctx = load_context(tmp_path_project)
        assert check_session_has_developer_md(ctx) == []

    def test_missing_artifact_fires(
        self,
        tmp_path_project,
        save_test_session,
        save_test_issue,
    ):
        _save_issue(save_test_issue, tmp_path_project, "TMP-1", status="in_review")
        save_test_session(tmp_path_project, "s1", status="in_review", issues=["TMP-1"])
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
        save_test_session(tmp_path_project, "s1", status="verified", issues=["TMP-1"])
        issue_docs_dir = tmp_path_project / "instances" / "issues" / "TMP-1" / "docs"
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
        save_test_session(tmp_path_project, "s1", status="verified", issues=["TMP-1"])
        # developer.md present (so the developer-md check doesn't noise),
        # but verified.md intentionally missing.
        (
            tmp_path_project
            / "instances"
            / "issues"
            / "TMP-1"
            / "docs"
            / "developer.md"
        ).parent.mkdir(parents=True, exist_ok=True)
        (
            tmp_path_project
            / "instances"
            / "issues"
            / "TMP-1"
            / "docs"
            / "developer.md"
        ).write_text("dev notes\n", encoding="utf-8")
        ctx = load_context(tmp_path_project)
        results = check_session_has_verified_md(ctx)
        assert any(r.code == "session/verified_md_missing" for r in results), (
            f"expected session/verified_md_missing, got {[r.code for r in results]}"
        )
