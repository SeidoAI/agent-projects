"""Tests for `tripwire.core.pr_summary_compute`.

Each test scaffolds a tiny git repo with two commits — base and head —
that represent two project states, then calls :func:`compute_pr_summary`
and asserts on the resulting :class:`PrSummary`.

The fixture repo uses the project layout the rest of the test suite
relies on (project.yaml + issues/sessions/nodes dirs) and writes minimal
valid models with the existing core save_* helpers, so the test stays
honest about what's actually persisted on disk at each SHA.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tripwire.core.pr_summary_compute import compute_pr_summary

# ============================================================================
# Helpers
# ============================================================================


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        msg,
    )
    return _git(repo, "rev-parse", "HEAD")


def _write_project(repo: Path, name: str = "fixture", key_prefix: str = "FIX") -> None:
    """Write a minimal valid project.yaml + dirs into *repo*."""
    (repo / "project.yaml").write_text(
        f"name: {name}\n"
        f"key_prefix: {key_prefix}\n"
        "next_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (repo / sub).mkdir(parents=True, exist_ok=True)
    # Minimal artifacts manifest so validate doesn't choke.
    artifacts = repo / "templates" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "manifest.yaml").write_text("artifacts: []\n", encoding="utf-8")


def _save_issue(repo: Path, key: str, status: str = "todo") -> None:
    from tripwire.core.store import save_issue
    from tripwire.models import Issue

    body = (
        "## Context\nseed.\n\n"
        "## Implements\nREQ-1\n\n"
        "## Repo scope\n- repo/x\n\n"
        "## Requirements\n- thing\n\n"
        "## Execution constraints\nIf ambiguous, stop and ask.\n\n"
        "## Acceptance criteria\n- [ ] thing\n\n"
        "## Test plan\n```\nuv run pytest\n```\n\n"
        "## Dependencies\nnone\n\n"
        "## Definition of Done\n- [ ] done\n"
    )
    save_issue(
        repo,
        Issue.model_validate(
            {
                "id": key,
                "title": f"Issue {key}",
                "status": status,
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
                "kind": "feat",
                "body": body,
            }
        ),
        update_cache=False,
    )


def _save_session(repo: Path, sid: str, status: str = "planned") -> None:
    from tripwire.core.session_store import save_session
    from tripwire.models import AgentSession

    save_session(
        repo,
        AgentSession.model_validate(
            {
                "id": sid,
                "name": f"Session {sid}",
                "agent": "backend-coder",
                "issues": [],
                "status": status,
                "repos": [],
            }
        ),
    )


def _save_node(
    repo: Path, nid: str, *, scope: str = "local", origin: str = "local"
) -> None:
    from tripwire.core.node_store import save_node
    from tripwire.models import ConceptNode

    save_node(
        repo,
        ConceptNode.model_validate(
            {
                "id": nid,
                "type": "model",
                "name": f"Node {nid}",
                "status": "active",
                "scope": scope,
                "origin": origin,
                "body": "Body.\n",
            }
        ),
        update_cache=False,
    )


# ============================================================================
# Fixture: two-commit fixture repo
# ============================================================================


@pytest.fixture
def repo_two_states(tmp_path: Path) -> tuple[Path, str, str]:
    """Repo with project at base SHA and a modified project at head SHA."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_project(repo)

    _save_issue(repo, "FIX-1", status="todo")
    _save_issue(repo, "FIX-2", status="in_progress")
    _save_issue(repo, "FIX-3", status="done")
    _save_session(repo, "alpha", status="planned")
    _save_node(repo, "common-node", scope="local", origin="local")

    base_sha = _commit_all(repo, "base")

    # Move FIX-1 todo→in_progress, FIX-2 in_progress→done; add FIX-4;
    # add a new node, promote common-node to workspace; transition session.
    _save_issue(repo, "FIX-1", status="in_progress")
    _save_issue(repo, "FIX-2", status="done")
    _save_issue(repo, "FIX-4", status="todo")
    _save_session(repo, "alpha", status="executing")
    _save_node(repo, "new-node", scope="local", origin="local")
    _save_node(repo, "common-node", scope="workspace", origin="workspace")

    head_sha = _commit_all(repo, "head")
    return repo, base_sha, head_sha


# ============================================================================
# Tests
# ============================================================================


def test_compute_returns_summary_with_both_shas(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)
    assert summary.base_sha == base_sha
    assert summary.head_sha == head_sha


def test_compute_records_project_name(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)
    assert summary.project_name == "fixture"


def test_compute_detects_issue_status_changes(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)

    by_id = {c.id: c for c in summary.issues.changes}
    assert by_id["FIX-1"].from_status == "todo"
    assert by_id["FIX-1"].to_status == "in_progress"
    assert by_id["FIX-2"].from_status == "in_progress"
    assert by_id["FIX-2"].to_status == "done"
    # Newly added issue shows as appearing
    assert by_id["FIX-4"].from_status == "—"
    assert by_id["FIX-4"].to_status == "todo"


def test_compute_records_per_status_counts(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)

    # Base: 1 todo, 1 in_progress, 1 done.
    assert summary.issues.base_counts == {
        "todo": 1,
        "in_progress": 1,
        "done": 1,
    }
    # Head: FIX-1 in_progress, FIX-2 done, FIX-3 done, FIX-4 todo
    assert summary.issues.head_counts == {
        "in_progress": 1,
        "done": 2,
        "todo": 1,
    }


def test_compute_detects_session_state_change(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)
    assert any(
        c.id == "alpha" and c.from_status == "planned" and c.to_status == "executing"
        for c in summary.sessions.changes
    )


def test_compute_detects_concept_graph_added_and_promoted(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)
    assert "new-node" in summary.concept_graph.nodes_added
    assert "common-node" in summary.concept_graph.nodes_promoted
    assert summary.concept_graph.nodes_removed == []


def test_compute_handles_base_with_no_project(tmp_path: Path):
    """When base SHA predates project.yaml, base state is empty and head shows
    everything as added."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    base_sha = _commit_all(repo, "before tripwire")

    _write_project(repo)
    _save_issue(repo, "FIX-1", status="todo")
    head_sha = _commit_all(repo, "tripwire init")

    summary = compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)
    assert summary.issues.base_counts == {}
    assert summary.issues.head_counts == {"todo": 1}
    by_id = {c.id: c for c in summary.issues.changes}
    assert by_id["FIX-1"].from_status == "—"


def test_compute_does_not_disturb_caller_working_tree(repo_two_states):
    repo, base_sha, head_sha = repo_two_states
    head_before = _git(repo, "rev-parse", "HEAD")
    issues_dir = repo / "issues"
    files_before = sorted(p.name for p in issues_dir.iterdir())

    compute_pr_summary(repo, base_sha=base_sha, head_sha=head_sha)

    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert sorted(p.name for p in issues_dir.iterdir()) == files_before
