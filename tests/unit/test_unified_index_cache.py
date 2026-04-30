"""Cache must walk session and comment files (KUI-132 / A7).

Before v0.9, the graph cache only fingerprinted issue and concept-node
files. The unified index requires every entity-type resolver to feed
the index — sessions and comments must contribute edges so the
`tripwire graph query` CLI returns cross-type results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from tripwire.core.graph.cache import full_rebuild
from tripwire.core.graph.index import UnifiedIndex
from tripwire.core.store import save_issue, save_project
from tripwire.models import Issue, ProjectConfig, RepoEntry


def _make_project(tmp_path: Path) -> Path:
    save_project(
        tmp_path,
        ProjectConfig(
            name="t",
            key_prefix="TST",
            repos={"SeidoAI/test-repo": RepoEntry()},
            next_issue_number=1,
        ),
    )
    return tmp_path


def _make_issue(project_dir: Path, key: str, body: str = "") -> None:
    issue = Issue(
        id=key,
        title=f"Test {key}",
        status="todo",
        priority="medium",
        executor="ai",
        verifier="required",
        body=body or f"Body for {key}.\n",
    )
    save_issue(project_dir, issue, update_cache=False)


def _write_session(project_dir: Path, sid: str, *, agent: str, issues: list[str], body: str = "") -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    fm = {
        "id": sid,
        "name": sid,
        "agent": agent,
        "issues": issues,
    }
    front = yaml.safe_dump(fm, sort_keys=False)
    text = f"---\n{front}---\n{body}"
    (sdir / "session.yaml").write_text(text, encoding="utf-8")


def _write_comment(
    project_dir: Path,
    issue_key: str,
    filename: str,
    *,
    author: str,
    type_: str,
    body: str = "",
) -> None:
    cdir = project_dir / "issues" / issue_key / "comments"
    cdir.mkdir(parents=True, exist_ok=True)
    fm = {
        "issue_key": issue_key,
        "author": author,
        "type": type_,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    front = yaml.safe_dump(fm, sort_keys=False)
    text = f"---\n{front}---\n{body}"
    (cdir / filename).write_text(text, encoding="utf-8")


def test_full_rebuild_emits_session_to_issue_refs(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _make_issue(tmp_path, "TST-2")
    _write_session(
        tmp_path,
        "session-foo",
        agent="developer",
        issues=["TST-1", "TST-2"],
    )

    cache = full_rebuild(tmp_path)

    # Session should appear as a fingerprinted file.
    session_rel = "sessions/session-foo/session.yaml"
    assert session_rel in cache.files

    # Edges from session to each issue, with canonical kind = refs.
    session_edges = [e for e in cache.edges if e.source_file == session_rel]
    targets = {(e.from_id, e.to_id, e.type) for e in session_edges}
    assert ("session-foo", "TST-1", "refs") in targets
    assert ("session-foo", "TST-2", "refs") in targets


def test_full_rebuild_emits_session_body_refs(tmp_path: Path) -> None:
    """Session body `[[node-id]]` (lowercase slug) refs must emit edges.

    The existing reference parser only matches lowercase slugs (see
    `core/graph/refs.py::REFERENCE_PATTERN`); uppercase issue keys
    like `KUI-1` are not picked up from prose. Sessions referencing
    a concept node by slug should emit a refs edge.
    """
    _make_project(tmp_path)
    _write_session(
        tmp_path,
        "session-bar",
        agent="developer",
        issues=[],
        body="See [[user-model]] for context.\n",
    )

    cache = full_rebuild(tmp_path)
    session_rel = "sessions/session-bar/session.yaml"
    body_edges = [
        e
        for e in cache.edges
        if e.source_file == session_rel and e.from_id == "session-bar"
    ]
    assert any(e.to_id == "user-model" and e.type == "refs" for e in body_edges)


def test_full_rebuild_emits_comment_to_issue_refs(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _write_comment(
        tmp_path,
        "TST-1",
        "01-pm-feedback-2026-04-30.yaml",
        author="agent:pm",
        type_="pm_feedback",
        body="See [[TST-1]] for the original.",
    )

    cache = full_rebuild(tmp_path)

    comment_rel = "issues/TST-1/comments/01-pm-feedback-2026-04-30.yaml"
    assert comment_rel in cache.files

    comment_edges = [e for e in cache.edges if e.source_file == comment_rel]
    # Comment → its issue, refs kind. Comment id is synthesized as
    # `<issue-key>:<filename-stem>`.
    expected_id = "TST-1:01-pm-feedback-2026-04-30"
    targets = {(e.from_id, e.to_id, e.type) for e in comment_edges}
    assert (expected_id, "TST-1", "refs") in targets


def test_unified_index_returns_session_when_querying_downstream_of_issue(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _write_session(
        tmp_path, "session-cross", agent="developer", issues=["TST-1"]
    )

    cache = full_rebuild(tmp_path)
    idx = UnifiedIndex(project_dir=tmp_path, cache=cache)

    # Downstream of TST-1 = things that point at TST-1. The session
    # references TST-1, so it should show up.
    downstream = set(idx.downstream("TST-1"))
    assert "session-cross" in downstream
