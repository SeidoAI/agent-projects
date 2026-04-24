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


class TestVerifyPrMerged:
    """`_verify_pr_merged` must require every worktree branch to have a
    merged PR (not just the first one found), and must invoke ``gh``
    from inside each worktree so gh picks up the correct remote when
    the two worktrees have different origins (v0.7.4 dual-PR case)."""

    def _make_session(self, worktrees):
        from tripwire.models.session import AgentSession, RuntimeState, WorktreeEntry

        entries = [WorktreeEntry(**w) for w in worktrees]
        return AgentSession.model_validate(
            {
                "id": "s1",
                "name": "t",
                "agent": "a",
                "runtime_state": RuntimeState(worktrees=entries).model_dump(),
            }
        )

    def _install_fake_run(self, monkeypatch, verdicts_by_branch):
        """Stub subprocess.run so each gh call returns merged/unmerged
        per ``verdicts_by_branch[<branch>]``. Captures every call's
        cwd + cmd for later assertion — this is what enforces that
        ``_verify_pr_merged`` runs gh from inside each worktree."""
        from tripwire.core import session_complete as mod

        calls: list[dict] = []

        def fake_run(cmd, **kwargs):
            branch = cmd[cmd.index("--head") + 1]
            calls.append({"cmd": cmd, "cwd": kwargs.get("cwd"), "branch": branch})

            class _R:
                returncode = 0
                stdout = '[{"number": 1}]' if verdicts_by_branch.get(branch) else "[]"

            return _R()

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        return calls

    def test_single_worktree_merged_passes(self, monkeypatch, tmp_path):
        """Pre-v0.7.4 regression guard."""
        from tripwire.core import session_complete as mod

        calls = self._install_fake_run(monkeypatch, {"feat/s1": True})
        session = self._make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                }
            ]
        )
        mod._verify_pr_merged(session)
        # gh was invoked from inside the worktree.
        assert calls[0]["cwd"] == str(tmp_path / "code-wt-s1")

    def test_single_worktree_unmerged_fails_with_branch_name(
        self, monkeypatch, tmp_path
    ):
        from tripwire.core import session_complete as mod

        self._install_fake_run(monkeypatch, {"feat/s1": False})
        session = self._make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                }
            ]
        )
        with pytest.raises(CompleteError) as exc:
            mod._verify_pr_merged(session)
        assert exc.value.code == "complete/pr_not_merged"
        assert "feat/s1" in str(exc.value)

    def test_all_branches_merged_passes_dual_worktree_with_per_worktree_cwd(
        self, monkeypatch, tmp_path
    ):
        """v0.7.4: both PRs merged → complete proceeds. Key content
        assertion: gh was invoked twice, each call's cwd matching the
        corresponding worktree path — proves the ``cwd=wt.worktree_path``
        behaviour that lets gh pick the right remote when the two
        worktrees have different origins."""
        from tripwire.core import session_complete as mod

        calls = self._install_fake_run(monkeypatch, {"feat/s1": True, "proj/s1": True})
        session = self._make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                },
                {
                    "repo": "proj-tracking",
                    "clone_path": str(tmp_path / "proj"),
                    "worktree_path": str(tmp_path / "proj-wt-s1"),
                    "branch": "proj/s1",
                },
            ]
        )
        mod._verify_pr_merged(session)
        # Each gh call ran from inside its own worktree.
        cwds_by_branch = {c["branch"]: c["cwd"] for c in calls}
        assert cwds_by_branch == {
            "feat/s1": str(tmp_path / "code-wt-s1"),
            "proj/s1": str(tmp_path / "proj-wt-s1"),
        }

    def test_one_branch_unmerged_fails_with_that_branch_name(
        self, monkeypatch, tmp_path
    ):
        """First branch merged, second not → complete refuses and names
        the unmerged branch. Pre-v0.7.4 semantics would have early-
        exited on the first merged PR and missed the second."""
        from tripwire.core import session_complete as mod

        calls = self._install_fake_run(monkeypatch, {"feat/s1": True, "proj/s1": False})
        session = self._make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                },
                {
                    "repo": "proj-tracking",
                    "clone_path": str(tmp_path / "proj"),
                    "worktree_path": str(tmp_path / "proj-wt-s1"),
                    "branch": "proj/s1",
                },
            ]
        )
        with pytest.raises(CompleteError) as exc:
            mod._verify_pr_merged(session)
        assert exc.value.code == "complete/pr_not_merged"
        assert "proj/s1" in str(exc.value)
        # feat/s1 merged, so should NOT be in the error message.
        assert "feat/s1" not in str(exc.value)
        # Content check: iterated all branches (didn't early-exit).
        assert len(calls) == 2

    def test_empty_worktrees_raises(self):
        from tripwire.core import session_complete as mod

        session = self._make_session([])
        with pytest.raises(CompleteError) as exc:
            mod._verify_pr_merged(session)
        assert exc.value.code == "complete/pr_not_merged"
        assert "no recorded worktrees" in str(exc.value)
