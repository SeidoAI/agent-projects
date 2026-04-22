"""session_complete gate logic (spec §11.2)."""

import json
from pathlib import Path

import pytest

from tripwire.core.session_complete import CompleteError, complete_session


def _write_review_json(
    project_dir: Path, session_id: str, *, exit_code: int, verdict: str
) -> None:
    p = project_dir / "sessions" / session_id / "review.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "verdict": verdict,
                "exit_code": exit_code,
                "pr_number": None,
                "head_sha": None,
                "timestamp": "2026-04-21T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def test_complete_refuses_non_completable_status(
    tmp_path_project: Path, save_test_session
):
    """Spec §11.2 step 1 — only {in_review, verified} complete without --force."""
    save_test_session(tmp_path_project, "s1", status="planned")
    with pytest.raises(CompleteError) as exc:
        complete_session(tmp_path_project, "s1", dry_run=True)
    assert exc.value.code == "complete/not_active"


def test_complete_refuses_in_progress_status(tmp_path_project: Path, save_test_session):
    """`in_progress`, `executing`, `active` require going through review first."""
    save_test_session(tmp_path_project, "s1", status="executing")
    with pytest.raises(CompleteError) as exc:
        complete_session(tmp_path_project, "s1", dry_run=True)
    assert exc.value.code == "complete/not_active"


def test_complete_refuses_without_artifacts(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    with pytest.raises(CompleteError) as exc:
        complete_session(
            tmp_path_project,
            "s1",
            dry_run=True,
            skip_pr_merge_check=True,
            force_review=True,
        )
    assert exc.value.code == "complete/missing_artifacts"


def test_complete_refuses_without_review_unless_force_review(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    """Spec §11.2 step 4 — review.json is required."""
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    # Without review.json → refuse with complete/no_review.
    with pytest.raises(CompleteError) as exc:
        complete_session(
            tmp_path_project,
            "s1",
            dry_run=True,
            skip_pr_merge_check=True,
        )
    assert exc.value.code == "complete/no_review"

    # --force-review bypasses.
    result = complete_session(
        tmp_path_project,
        "s1",
        dry_run=True,
        skip_pr_merge_check=True,
        force_review=True,
    )
    assert result.session_id == "s1"


def test_complete_refuses_on_failed_review(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    """Spec §11.2 step 4 — exit_code > 1 blocks complete."""
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    _write_review_json(tmp_path_project, "s1", exit_code=2, verdict="rejected")

    with pytest.raises(CompleteError) as exc:
        complete_session(
            tmp_path_project,
            "s1",
            dry_run=True,
            skip_pr_merge_check=True,
        )
    assert exc.value.code == "complete/review_failed"


def test_complete_dry_run_passes_when_gates_satisfied(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    _write_review_json(tmp_path_project, "s1", exit_code=0, verdict="approved")

    result = complete_session(
        tmp_path_project,
        "s1",
        dry_run=True,
        skip_pr_merge_check=True,
    )
    assert result.session_id == "s1"


def test_complete_closes_issues_and_transitions_session(
    tmp_path_project: Path, save_test_session, save_test_issue
):
    save_test_issue(tmp_path_project, "TMP-1", status="in_review")
    (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
        "# notes\n", encoding="utf-8"
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="in_review",
        issues=["TMP-1"],
    )
    _write_review_json(tmp_path_project, "s1", exit_code=0, verdict="approved")

    result = complete_session(
        tmp_path_project,
        "s1",
        skip_pr_merge_check=True,
        skip_worktree_cleanup=True,
    )
    assert "TMP-1" in result.issues_closed

    from tripwire.core.session_store import load_session
    from tripwire.core.store import load_issue

    issue = load_issue(tmp_path_project, "TMP-1")
    assert issue.status == "done"
    session = load_session(tmp_path_project, "s1")
    assert session.status == "done"


def test_complete_force_bypasses_gates(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1", status="planned")
    result = complete_session(
        tmp_path_project,
        "s1",
        force=True,
        dry_run=True,
        skip_pr_merge_check=True,
        skip_artifact_check=True,
    )
    assert result.session_id == "s1"


class TestCompleteInvokesPrFlow:
    def test_complete_runs_pr_flow_after_gates(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        """A happy-path complete should invoke run_pr_flow and record
        the resulting PR URLs on the latest engagement."""
        import subprocess as _sp
        from datetime import datetime, timezone

        from tripwire.core.session_complete import complete_session
        from tripwire.core.session_store import load_session
        from tripwire.models.session import EngagementEntry

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _sp.run(["git", "init", "-q", "-b", "main"], cwd=code_wt, check=True)
        _sp.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-q", "-m", "init"],
            cwd=code_wt, check=True,
        )
        _sp.run(
            ["git", "checkout", "-q", "-b", "feat/s1"],
            cwd=code_wt, check=True,
        )
        (code_wt / "f.txt").write_text("x")
        _sp.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "f.txt"], cwd=code_wt, check=True,
        )
        _sp.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "-m", "work"], cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="in_review",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
            engagements=[
                {
                    "started_at": datetime.now(tz=timezone.utc).isoformat(),
                    "trigger": "initial_launch",
                }
            ],
        )

        result = complete_session(
            tmp_path_project,
            "s1",
            dry_run=False,
            force=True,
            force_review=True,
            skip_artifact_check=True,
            skip_worktree_cleanup=True,
            skip_pr_flow_push=True,
        )

        pr_calls = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]
        ]
        assert len(pr_calls) == 1

        s = load_session(tmp_path_project, "s1")
        assert s.status == "done"
        assert s.engagements[-1].pr_urls
        assert s.engagements[-1].pr_urls[0].startswith("https://")
