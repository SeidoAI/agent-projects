"""Tests for v0.7.5 A — flipping draft PRs to ready at session complete.

``complete_session`` calls a new ``_flip_drafts_to_ready`` step that
runs ``gh pr ready <draft-pr-url>`` per worktree. Worktrees without
``draft_pr_url`` (legacy in-flight sessions that started pre-v0.7.5)
fall back to ``gh pr create`` so a PR exists to merge.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core import session_complete as mod
from tripwire.models.session import AgentSession, RuntimeState, WorktreeEntry


def _make_session(worktrees):
    entries = [WorktreeEntry(**w) for w in worktrees]
    return AgentSession.model_validate(
        {
            "id": "s1",
            "name": "t",
            "agent": "a",
            "runtime_state": RuntimeState(worktrees=entries).model_dump(),
        }
    )


class TestFlipDraftsToReady:
    def test_calls_gh_pr_ready_per_worktree_with_draft_pr_url(
        self, monkeypatch, tmp_path
    ):
        calls: list[dict] = []

        def fake_run(cmd, **kwargs):
            calls.append({"cmd": list(cmd), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()

        monkeypatch.setattr(mod.subprocess, "run", fake_run)

        session = _make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                    "draft_pr_url": "https://github.com/test/code/pull/10",
                },
                {
                    "repo": "tripwire-v0",
                    "clone_path": str(tmp_path / "proj"),
                    "worktree_path": str(tmp_path / "proj-wt-s1"),
                    "branch": "proj/s1",
                    "draft_pr_url": "https://github.com/test/proj/pull/11",
                },
            ]
        )

        mod._flip_drafts_to_ready(session)

        ready_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "ready"]]
        assert len(ready_calls) == 2
        assert ready_calls[0]["cmd"] == [
            "gh",
            "pr",
            "ready",
            "https://github.com/test/code/pull/10",
        ]
        assert ready_calls[0]["cwd"] == str(tmp_path / "code-wt-s1")
        assert ready_calls[1]["cmd"] == [
            "gh",
            "pr",
            "ready",
            "https://github.com/test/proj/pull/11",
        ]
        assert ready_calls[1]["cwd"] == str(tmp_path / "proj-wt-s1")

    def test_falls_back_to_gh_pr_create_when_no_draft_url(self, monkeypatch, tmp_path):
        """Sessions started before v0.7.5 have no ``draft_pr_url`` —
        complete must create a PR via ``gh pr create`` instead."""
        calls: list[dict] = []

        def fake_run(cmd, **kwargs):
            calls.append({"cmd": list(cmd), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()

        monkeypatch.setattr(mod.subprocess, "run", fake_run)

        session = _make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                    "draft_pr_url": None,
                },
            ]
        )

        mod._flip_drafts_to_ready(session)

        # No `gh pr ready` was attempted.
        assert not any(c["cmd"][:3] == ["gh", "pr", "ready"] for c in calls)
        # `gh pr create` ran from the worktree.
        create_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "create"]]
        assert len(create_calls) == 1
        assert create_calls[0]["cwd"] == str(tmp_path / "code-wt-s1")
        assert "--head" in create_calls[0]["cmd"]
        head_idx = create_calls[0]["cmd"].index("--head")
        assert create_calls[0]["cmd"][head_idx + 1] == "feat/s1"

    def test_mixed_draft_and_no_draft_per_worktree(self, monkeypatch, tmp_path):
        """One worktree opened a draft (v0.7.5 path), the other didn't
        (legacy / remote-less). Each worktree gets the matching call."""
        calls: list[dict] = []

        def fake_run(cmd, **kwargs):
            calls.append({"cmd": list(cmd), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            return _R()

        monkeypatch.setattr(mod.subprocess, "run", fake_run)

        session = _make_session(
            [
                {
                    "repo": "SeidoAI/code",
                    "clone_path": str(tmp_path / "code"),
                    "worktree_path": str(tmp_path / "code-wt-s1"),
                    "branch": "feat/s1",
                    "draft_pr_url": "https://github.com/test/code/pull/10",
                },
                {
                    "repo": "tripwire-v0",
                    "clone_path": str(tmp_path / "proj"),
                    "worktree_path": str(tmp_path / "proj-wt-s1"),
                    "branch": "proj/s1",
                    "draft_pr_url": None,
                },
            ]
        )

        mod._flip_drafts_to_ready(session)

        ready_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "ready"]]
        create_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "create"]]
        assert len(ready_calls) == 1
        assert len(create_calls) == 1
        assert ready_calls[0]["cwd"] == str(tmp_path / "code-wt-s1")
        assert create_calls[0]["cwd"] == str(tmp_path / "proj-wt-s1")


class TestCompleteSessionInvokesFlip:
    """End-to-end sanity: ``complete_session`` runs ``_flip_drafts_to_ready``
    so v0.7.5 sessions actually have their drafts flipped at complete-time.

    Drives through the real state machine — review.json present, issue
    artifacts present, PR-merged gate stubbed. v0.7.9 §A4: there are no
    bypass flags to take the shortcut path."""

    def test_complete_invokes_flip_drafts_to_ready(
        self,
        tmp_path_project: Path,
        save_test_session,
        save_test_issue,
        monkeypatch,
    ):
        import json

        from tripwire.core.session_complete import complete_session

        save_test_issue(tmp_path_project, "TMP-1", status="in_review")
        (tmp_path_project / "issues" / "TMP-1" / "developer.md").write_text(
            "# notes\n", encoding="utf-8"
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="in_review",
            issues=["TMP-1"],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt-s1",
                        "branch": "feat/s1",
                        "draft_pr_url": "https://github.com/test/code/pull/10",
                    },
                ]
            },
        )
        # review.json (gate 4) must be present and exit_code <= 1.
        review_path = tmp_path_project / "sessions" / "s1" / "review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {
                    "session_id": "s1",
                    "verdict": "approved",
                    "exit_code": 0,
                    "pr_number": None,
                    "head_sha": None,
                    "timestamp": "2026-04-25T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        # PR-merged gate: stubbed to a no-op (the gate that needs gh).
        monkeypatch.setattr(mod, "_verify_pr_merged", lambda _session: None)

        called: list = []

        def fake_flip(session):
            called.append(session.id)

        monkeypatch.setattr(mod, "_flip_drafts_to_ready", fake_flip)

        complete_session(tmp_path_project, "s1", dry_run=True)

        assert called == ["s1"]
