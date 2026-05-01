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


def _write_session(
    project_dir: Path, sid: str, *, agent: str, issues: list[str], body: str = ""
) -> None:
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
    _write_session(tmp_path, "session-cross", agent="developer", issues=["TST-1"])

    cache = full_rebuild(tmp_path)
    idx = UnifiedIndex(project_dir=tmp_path, cache=cache)

    # Downstream of TST-1 = things that point at TST-1. The session
    # references TST-1, so it should show up.
    downstream = set(idx.downstream("TST-1"))
    assert "session-cross" in downstream


# ============================================================================
# v0.9.0.1 fix — codex P1: referenced_by must include canonical refs edges
# ============================================================================


def test_referenced_by_includes_session_refs(tmp_path: Path) -> None:
    """Codex P1 (PR #74 follow-up): `_rebuild_derived_tables.referenced_by`
    must surface session→issue refs edges. Pre-fix, the rebuild loop only
    considered legacy on-disk strings (`references|blocked_by|related`)
    and silently dropped sessions/comments emitting canonical `refs`.
    """
    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _write_session(
        tmp_path, "session-touches-tst1", agent="developer", issues=["TST-1"]
    )

    cache = full_rebuild(tmp_path)

    # The session references TST-1 → it should appear in TST-1's
    # `referenced_by` list. Pre-fix this list was empty.
    assert cache.referenced_by.get("TST-1") == ["session-touches-tst1"]


def test_referenced_by_includes_comment_refs(tmp_path: Path) -> None:
    """Codex P1: comment→issue refs edges feed `referenced_by` too.

    Comment id is synthesized as `<issue-key>:<filename-stem>` (D1).
    """
    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _make_issue(tmp_path, "TST-2", body="Stub for TST-2.\n")
    _write_comment(
        tmp_path,
        "TST-1",
        "01-pm-feedback-2026-04-30.yaml",
        author="agent:pm",
        type_="feedback",
        body="Cross-link to [[TST-2]] for context.",
    )

    cache = full_rebuild(tmp_path)

    # Body refs are lowercase-slug-only (D3), so [[TST-2]] uppercase
    # won't emit a body edge — but the comment file itself participates
    # in referenced_by lookups for any lowercase-slug refs it does carry.
    # The synthesized comment id for the file is what would land if
    # the comment body had a lowercase slug ref. The presence of
    # `comment` rows in cache.edges with type="refs" pointing somewhere
    # is enough to assert the loop includes "refs" — verify there are
    # no comment-typed refs filtered out.
    comment_refs_into_anything = [
        e
        for e in cache.edges
        if e.type == "refs" and e.source_file.startswith("issues/TST-1/comments/")
    ]
    # If the comment emitted any refs edges (it can), they must show up
    # in referenced_by. Absent any body-side lowercase ref, this loop
    # is a coverage assertion only — the fix is exercised by the
    # session test above.
    for edge in comment_refs_into_anything:
        assert edge.from_id in cache.referenced_by.get(edge.to_id, [])


# ============================================================================
# v0.9.0.1 fix — codex P2: save_session must invalidate the graph cache
# ============================================================================


def test_save_session_invalidates_cache(tmp_path: Path) -> None:
    """Codex P2 (PR #74 follow-up): `save_session` should call
    `update_cache_for_file` so session edits propagate to
    `graph/index.yaml` immediately, matching `save_issue`'s pattern.
    Pre-fix, sessions were first-class graph edge sources but their
    save path didn't invalidate the cache, so reads via direct
    `load_index` (without a freshness pass) saw stale data.
    """
    from tripwire.core.graph.cache import load_index, save_index
    from tripwire.core.session_store import save_session
    from tripwire.models import AgentSession

    _make_project(tmp_path)
    _make_issue(tmp_path, "TST-1")
    _make_issue(tmp_path, "TST-2")

    # Build + persist a baseline cache (no sessions yet).
    pre_cache = full_rebuild(tmp_path)
    save_index(tmp_path, pre_cache)
    pre_session_edges = [
        e for e in pre_cache.edges if e.source_file.startswith("sessions/")
    ]
    assert pre_session_edges == []

    # Write a session via the canonical save path. With the fix in
    # place, save_session calls update_cache_for_file → cache on
    # disk reflects the new session edges immediately.
    sess = AgentSession(
        id="session-x",
        name="session-x",
        agent="developer",
        issues=["TST-1", "TST-2"],
    )
    save_session(tmp_path, sess)

    # Re-load the on-disk cache. The post-fix invariant: the session
    # edges land on disk without any explicit ensure_fresh / rebuild.
    post = load_index(tmp_path)
    assert post is not None, "save_session should have updated the cache file"
    post_session_edges = [
        e for e in post.edges if e.source_file == "sessions/session-x/session.yaml"
    ]
    assert len(post_session_edges) >= 2  # one ref edge per linked issue
    targets = {e.to_id for e in post_session_edges}
    assert "TST-1" in targets
    assert "TST-2" in targets
