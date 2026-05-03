"""Incremental graph index cache (v2 schema).

`graph/index.yaml` is committed to git as a derived view of the underlying
issue and node files. It is never the source of truth — deleting it always
rebuilds correctly from the files. The cache exists purely so UI and CLI
reads are O(1) instead of rescanning N files every time.

The cache tracks:
- Per-file fingerprints (mtime + sha + extracted edge data) used to detect
  what changed on incremental update
- Computed lookup tables (`by_name`, `by_type`, `referenced_by`) that power
  fast CLI and UI reads
- A flat list of edges with `source_file` so `update_cache_for_file` can
  surgically remove edges produced by a single file and re-emit them

Two entry points:
- `update_cache_for_file(project_dir, rel_path)` — incremental update for
  one file (called on every file change)
- `full_rebuild(project_dir)` — scan everything and rebuild from scratch
  (called when the cache is missing, corrupt, or version-mismatched)

The dispatcher `ensure_fresh(project_dir)` picks between the two based on
the current state of the cache and the filesystem. It returns True if any
rebuild happened.
"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from tripwire.core import paths
from tripwire.core.graph.refs import extract_references
from tripwire.core.parser import parse_frontmatter_body
from tripwire.models.graph import FileFingerprint, GraphEdge, GraphIndex
from tripwire.models.issue import Issue
from tripwire.models.node import ConceptNode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Backwards-compatible aliases — prefer importing from `tripwire.core.paths`.
INDEX_REL_PATH = paths.GRAPH_CACHE
LOCK_REL_PATH = paths.GRAPH_LOCK
CACHE_VERSION = 2

ISSUES_PREFIX = f"{paths.ISSUES_DIR}/"
NODES_PREFIX = f"{paths.NODES_DIR}/"
SESSIONS_PREFIX = f"{paths.SESSIONS_DIR}/"
COMMENTS_SUBDIR = paths.COMMENTS_SUBDIR


# ============================================================================
# Locking
# ============================================================================


DEFAULT_LOCK_TIMEOUT_S = 10.0
LOCK_POLL_INTERVAL_S = 0.05

# In ensure_fresh, switch from per-file incremental updates to a single
# full rebuild once the change set crosses this many files. The
# incremental path is O(N²) because update_cache_for_file rebuilds the
# derived tables on every call; full_rebuild does it once. Below the
# threshold the incremental path is still cheaper (no whole-tree scan).
_INCREMENTAL_BAILOUT = 5


@contextmanager
def _index_lock(
    project_dir: Path, timeout_s: float = DEFAULT_LOCK_TIMEOUT_S
) -> Iterator[None]:
    """Acquire an exclusive `flock` on the graph index lock file.

    Creates `graph/.index.lock` if it doesn't exist. Same polling pattern as
    `core/key_allocator.py`.
    """
    lock_path = project_dir / LOCK_REL_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)

    deadline = time.monotonic() + timeout_s
    with lock_path.open("a") as fh:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock {lock_path} within {timeout_s}s."
                    ) from None
                time.sleep(LOCK_POLL_INTERVAL_S)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ============================================================================
# Load / save
# ============================================================================


def load_index(project_dir: Path) -> GraphIndex | None:
    """Load `graph/index.yaml`, or return None if the file is missing.

    Version mismatch and parse errors also return None — the caller (usually
    `ensure_fresh`) will then trigger a full rebuild. This is intentional:
    a corrupt cache is trivially recoverable by rebuilding from the files.
    """
    path = project_dir / INDEX_REL_PATH
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != CACHE_VERSION:
        return None
    try:
        return GraphIndex.model_validate(raw)
    except ValueError:
        return None


def save_index(project_dir: Path, cache: GraphIndex) -> None:
    """Write the cache to `graph/index.yaml` atomically.

    Uses a tmp-file + rename so partial writes never leave a corrupt cache
    on disk.
    """
    path = project_dir / INDEX_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    # `by_alias=True` so GraphEdge serialises with the `from`/`to` keys that
    # match the spec's YAML schema, not the Python `from_id`/`to_id` names.
    data = cache.model_dump(mode="json", by_alias=True, exclude_none=True)
    tmp.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def _empty_cache() -> GraphIndex:
    """Return an empty GraphIndex ready to be populated."""
    return GraphIndex(version=CACHE_VERSION)


# ============================================================================
# Path helpers
# ============================================================================


def issue_key_from_rel_path(rel_path: str) -> str | None:
    """Extract the issue key from `issues/<KEY>/issue.yaml`."""
    if not rel_path.startswith(ISSUES_PREFIX):
        return None
    p = Path(rel_path)
    if p.name != paths.ISSUE_FILENAME:
        return None
    # `issues/<KEY>/issue.yaml` → parent dir name is the key
    return p.parent.name


def node_id_from_rel_path(rel_path: str) -> str | None:
    """Extract the node id from `<NODES_DIR>/<id>.yaml`."""
    if not rel_path.startswith(NODES_PREFIX):
        return None
    p = Path(rel_path)
    if p.suffix != ".yaml":
        return None
    return p.stem


def _classify(rel_path: str) -> str | None:
    """Return `"issue"`, `"node"`, `"session"`, `"comment"`, or None.

    KUI-132 / A7 added `session` and `comment` so the unified index
    carries cross-type edges from those entities.
    """
    if rel_path.startswith(ISSUES_PREFIX) and rel_path.endswith(
        f"/{paths.ISSUE_FILENAME}"
    ):
        return "issue"
    if rel_path.startswith(NODES_PREFIX) and rel_path.endswith(".yaml"):
        return "node"
    if rel_path.startswith(SESSIONS_PREFIX) and rel_path.endswith(
        f"/{paths.SESSION_FILENAME}"
    ):
        return "session"
    if (
        rel_path.startswith(ISSUES_PREFIX)
        and f"/{COMMENTS_SUBDIR}/" in rel_path
        and rel_path.endswith(".yaml")
    ):
        return "comment"
    return None


def session_id_from_rel_path(rel_path: str) -> str | None:
    """Extract the session id from `sessions/<id>/session.yaml`."""
    if not rel_path.startswith(SESSIONS_PREFIX):
        return None
    p = Path(rel_path)
    if p.name != paths.SESSION_FILENAME:
        return None
    return p.parent.name


def comment_id_from_rel_path(rel_path: str) -> str | None:
    """Synthesize a comment id from `issues/<KEY>/comments/<stem>.yaml`.

    The Comment model has no `id` field — only a UUID. The unified
    index uses `<issue-key>:<filename-stem>` so the id is stable
    across runs and dereferenceable from the cache.
    """
    if not rel_path.startswith(ISSUES_PREFIX):
        return None
    if f"/{COMMENTS_SUBDIR}/" not in rel_path:
        return None
    p = Path(rel_path)
    if p.suffix != ".yaml":
        return None
    # parts: ["issues", "<KEY>", "comments", "<stem>.yaml"]
    parts = p.parts
    if len(parts) < 4:
        return None
    issue_key = parts[1]
    stem = p.stem
    return f"{issue_key}:{stem}"


# ============================================================================
# Fingerprinting
# ============================================================================


def _compute_file_sha(path: Path) -> str:
    """Return `sha256:<hex>` of the file contents."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _fingerprint_issue(issue: Issue, abs_path: Path, body: str) -> FileFingerprint:
    references_to = list(
        dict.fromkeys(extract_references(body))
    )  # dedup, preserve order
    return FileFingerprint(
        mtime=abs_path.stat().st_mtime,
        sha=_compute_file_sha(abs_path),
        references_to=references_to,
        blocked_by=list(issue.blocked_by),
        blocks=[],  # computed in a second pass after all files are loaded
        related=[],
        parent=issue.parent,
    )


def _fingerprint_node(node: ConceptNode, abs_path: Path, body: str) -> FileFingerprint:
    references_to = list(dict.fromkeys(extract_references(body)))
    return FileFingerprint(
        mtime=abs_path.stat().st_mtime,
        sha=_compute_file_sha(abs_path),
        references_to=references_to,
        blocked_by=[],
        blocks=[],
        related=list(node.related),
        parent=None,
    )


def _fingerprint_session(abs_path: Path, body: str) -> FileFingerprint:
    """Fingerprint a session file. Sessions only contribute body refs and
    cross-type edges; the FileFingerprint shape matches the issue/node one
    with empty per-type fields."""
    references_to = list(dict.fromkeys(extract_references(body)))
    return FileFingerprint(
        mtime=abs_path.stat().st_mtime,
        sha=_compute_file_sha(abs_path),
        references_to=references_to,
        blocked_by=[],
        blocks=[],
        related=[],
        parent=None,
    )


def _fingerprint_comment(abs_path: Path, body: str) -> FileFingerprint:
    references_to = list(dict.fromkeys(extract_references(body)))
    return FileFingerprint(
        mtime=abs_path.stat().st_mtime,
        sha=_compute_file_sha(abs_path),
        references_to=references_to,
        blocked_by=[],
        blocks=[],
        related=[],
        parent=None,
    )


# ============================================================================
# Edge extraction
# ============================================================================


def _issue_edges(issue: Issue, rel_path: str, body: str) -> list[GraphEdge]:
    """Emit every edge sourced from a single issue file."""
    edges: list[GraphEdge] = []

    # [[node-id]] in body → references
    seen_refs: set[str] = set()
    for ref in extract_references(body):
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        edges.append(
            GraphEdge(
                from_id=issue.id,
                to_id=ref,
                type="references",
                source_file=rel_path,
            )
        )

    # blocked_by → blocked_by edges
    for blocker in issue.blocked_by:
        edges.append(
            GraphEdge(
                from_id=issue.id,
                to_id=blocker,
                type="blocked_by",
                source_file=rel_path,
            )
        )

    # parent → parent edge
    if issue.parent:
        edges.append(
            GraphEdge(
                from_id=issue.id,
                to_id=issue.parent,
                type="parent",
                source_file=rel_path,
            )
        )

    # implements → implements edges
    for req in issue.implements:
        edges.append(
            GraphEdge(
                from_id=issue.id,
                to_id=req,
                type="implements",
                source_file=rel_path,
            )
        )

    return edges


def _session_edges(
    session_id: str,
    rel_path: str,
    issues: list[str],
    body: str,
) -> list[GraphEdge]:
    """Emit edges sourced from a single session file.

    KUI-132 / A7. Session → issue edges land under canonical `refs`
    (per the legacy→canonical mapping in `core.graph.index`), so the
    unified `tripwire graph query downstream <issue>` returns sessions
    that work on that issue.
    """
    edges: list[GraphEdge] = []
    seen: set[str] = set()
    # Session.issues[] → refs to each issue
    for issue_key in issues:
        if issue_key in seen:
            continue
        seen.add(issue_key)
        edges.append(
            GraphEdge(
                from_id=session_id,
                to_id=issue_key,
                type="refs",
                source_file=rel_path,
                via_artifact=rel_path,
            )
        )
    # Body refs
    for ref in extract_references(body):
        if ref in seen:
            continue
        seen.add(ref)
        edges.append(
            GraphEdge(
                from_id=session_id,
                to_id=ref,
                type="refs",
                source_file=rel_path,
                via_artifact=rel_path,
            )
        )
    return edges


def _comment_edges(
    comment_id: str,
    rel_path: str,
    issue_key: str,
    body: str,
) -> list[GraphEdge]:
    """Emit edges sourced from a single comment file.

    KUI-132 / A7. The comment's parent issue gets a refs edge. Body
    `[[id]]` references emit additional refs edges.
    """
    edges: list[GraphEdge] = []
    seen: set[str] = set()
    # Comment → its issue (refs)
    edges.append(
        GraphEdge(
            from_id=comment_id,
            to_id=issue_key,
            type="refs",
            source_file=rel_path,
            via_artifact=rel_path,
        )
    )
    seen.add(issue_key)
    # Body refs
    for ref in extract_references(body):
        if ref in seen:
            continue
        seen.add(ref)
        edges.append(
            GraphEdge(
                from_id=comment_id,
                to_id=ref,
                type="refs",
                source_file=rel_path,
                via_artifact=rel_path,
            )
        )
    return edges


def _node_edges(node: ConceptNode, rel_path: str, body: str) -> list[GraphEdge]:
    """Emit every edge sourced from a single node file."""
    edges: list[GraphEdge] = []

    # related → related edges
    for related_id in node.related:
        edges.append(
            GraphEdge(
                from_id=node.id,
                to_id=related_id,
                type="related",
                source_file=rel_path,
            )
        )

    # [[refs]] in body also produce edges, even from node bodies
    seen_refs: set[str] = set()
    for ref in extract_references(body):
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        edges.append(
            GraphEdge(
                from_id=node.id,
                to_id=ref,
                type="references",
                source_file=rel_path,
            )
        )

    return edges


# ============================================================================
# Derived table rebuild
# ============================================================================


def _load_issue_file(project_dir: Path, rel_path: str) -> tuple[Issue, str] | None:
    """Parse an issue file from disk, returning (model, body) or None on error."""
    abs_path = project_dir / rel_path
    if not abs_path.exists():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter_body(text)
        model = Issue.model_validate({**fm, "body": body})
    except (OSError, ValueError):
        return None
    return model, body


def _load_node_file(project_dir: Path, rel_path: str) -> tuple[ConceptNode, str] | None:
    """Parse a concept node file from disk, returning (model, body) or None on error."""
    abs_path = project_dir / rel_path
    if not abs_path.exists():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter_body(text)
        model = ConceptNode.model_validate({**fm, "body": body})
    except (OSError, ValueError):
        return None
    return model, body


def _load_session_file(
    project_dir: Path, rel_path: str
) -> tuple[list[str], str] | None:
    """Parse a session file. Returns (issues, body) or None.

    KUI-132 / A7. The cache only needs the issues list and the body for
    edge extraction; full validation lives in the validator.
    """
    abs_path = project_dir / rel_path
    if not abs_path.exists():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter_body(text)
    except (OSError, ValueError):
        return None
    raw_issues = fm.get("issues") or []
    if not isinstance(raw_issues, list):
        return None
    issues = [str(i) for i in raw_issues]
    return issues, body


def _load_comment_file(project_dir: Path, rel_path: str) -> tuple[str, str] | None:
    """Parse a comment file. Returns (issue_key, body) or None."""
    abs_path = project_dir / rel_path
    if not abs_path.exists():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter_body(text)
    except (OSError, ValueError):
        return None
    issue_key = fm.get("issue_key")
    if not isinstance(issue_key, str) or not issue_key:
        return None
    return issue_key, body


def _rebuild_blocks(cache: GraphIndex) -> None:
    """Populate every issue file's `blocks` list from the inverse of `blocked_by`.

    This is an O(N) pass we run at the end of any cache mutation. The
    `blocks` field is a derived convenience — the source of truth is
    `blocked_by` on each issue file.
    """
    # Reset all blocks lists first
    for fp in cache.files.values():
        fp.blocks = []

    key_to_rel: dict[str, str] = {}
    for rel, _fp in cache.files.items():
        key = issue_key_from_rel_path(rel)
        if key is not None:
            key_to_rel[key] = rel

    for rel, fp in cache.files.items():
        source_key = issue_key_from_rel_path(rel)
        if source_key is None:
            continue
        for blocker in fp.blocked_by:
            target_rel = key_to_rel.get(blocker)
            if target_rel and source_key not in cache.files[target_rel].blocks:
                cache.files[target_rel].blocks.append(source_key)


def _rebuild_derived_tables(cache: GraphIndex, project_dir: Path) -> None:
    """Rebuild `by_name`, `by_type`, `referenced_by` from the current file set.

    These are the fast read paths the CLI and UI use. They are always
    derived from the files and edges — never authoritative.
    """
    by_name: dict[str, str] = {}
    by_type: dict[str, list[str]] = {}
    referenced_by: dict[str, list[str]] = {}

    # by_name and by_type are populated by reading the node files (we only
    # need their `name` and `type` fields, which aren't in the fingerprint).
    for rel in cache.files:
        if not rel.startswith(NODES_PREFIX):
            continue
        parsed = _load_node_file(project_dir, rel)
        if parsed is None:
            continue
        node, _ = parsed
        if node.name:
            by_name[node.name] = node.id
        by_type.setdefault(node.type, []).append(node.id)

    # Sort the node id lists for stable output.
    for entries in by_type.values():
        entries.sort()

    # `referenced_by` is the inverse of every "this references that" edge —
    # legacy on-disk strings ("references", "blocked_by", "related") AND the
    # canonical v0.9 EdgeKind values ("refs", "depends_on") emitted by
    # session/comment resolvers. Without "refs"/"depends_on" here, sessions
    # or comments that reference an issue or node would be invisible to
    # consumers that read `cache.referenced_by` (reverse-ref counts, "is
    # this node referenced anywhere?" lookups).
    _REFERENCING_EDGE_TYPES = (
        "references",
        "blocked_by",
        "related",
        "refs",
        "depends_on",
    )
    for edge in cache.edges:
        if edge.type in _REFERENCING_EDGE_TYPES:
            referenced_by.setdefault(edge.to_id, []).append(edge.from_id)

    for entries in referenced_by.values():
        entries.sort()

    cache.by_name = by_name
    cache.by_type = by_type
    cache.referenced_by = referenced_by


# ============================================================================
# Full rebuild
# ============================================================================


def full_rebuild(project_dir: Path) -> GraphIndex:
    """Scan every issue and node file and build the cache from scratch.

    Called when the cache is missing, version-mismatched, or corrupt. Also
    a handy forcing function if you ever suspect the cache is wrong —
    delete `graph/index.yaml` and run `validate`.
    """
    logger.info("graph_cache: full rebuild starting (project=%s)", project_dir)
    started = time.monotonic()
    with _index_lock(project_dir):
        cache = _empty_cache()

        # Pass 1: issue files (issues/<KEY>/issue.yaml)
        issues_root = paths.issues_dir(project_dir)
        if issues_root.is_dir():
            for idir in sorted(p for p in issues_root.iterdir() if p.is_dir()):
                if idir.name.startswith("."):
                    continue
                abs_path = idir / paths.ISSUE_FILENAME
                if not abs_path.is_file():
                    continue
                rel_path = str(abs_path.relative_to(project_dir))
                parsed = _load_issue_file(project_dir, rel_path)
                if parsed is None:
                    continue
                issue, body = parsed
                cache.files[rel_path] = _fingerprint_issue(issue, abs_path, body)
                cache.edges.extend(_issue_edges(issue, rel_path, body))

        # Pass 2: node files
        nodes_root = paths.nodes_dir(project_dir)
        if nodes_root.is_dir():
            for abs_path in sorted(nodes_root.glob("*.yaml")):
                rel_path = str(abs_path.relative_to(project_dir))
                parsed = _load_node_file(project_dir, rel_path)
                if parsed is None:
                    continue
                node, body = parsed
                cache.files[rel_path] = _fingerprint_node(node, abs_path, body)
                cache.edges.extend(_node_edges(node, rel_path, body))

        # Pass 3: session files (KUI-132 / A7)
        sessions_root = paths.sessions_dir(project_dir)
        if sessions_root.is_dir():
            for sdir in sorted(p for p in sessions_root.iterdir() if p.is_dir()):
                if sdir.name.startswith("."):
                    continue
                abs_path = sdir / paths.SESSION_FILENAME
                if not abs_path.is_file():
                    continue
                rel_path = str(abs_path.relative_to(project_dir))
                parsed_sess = _load_session_file(project_dir, rel_path)
                if parsed_sess is None:
                    continue
                issues, body = parsed_sess
                cache.files[rel_path] = _fingerprint_session(abs_path, body)
                cache.edges.extend(_session_edges(sdir.name, rel_path, issues, body))

        # Pass 4: comment files (KUI-132 / A7)
        if issues_root.is_dir():
            for idir in sorted(p for p in issues_root.iterdir() if p.is_dir()):
                if idir.name.startswith("."):
                    continue
                comments_root = idir / paths.COMMENTS_SUBDIR
                if not comments_root.is_dir():
                    continue
                for abs_path in sorted(comments_root.glob("*.yaml")):
                    rel_path = str(abs_path.relative_to(project_dir))
                    parsed_cmt = _load_comment_file(project_dir, rel_path)
                    if parsed_cmt is None:
                        continue
                    issue_key, body = parsed_cmt
                    comment_id = comment_id_from_rel_path(rel_path)
                    if comment_id is None:
                        continue
                    cache.files[rel_path] = _fingerprint_comment(abs_path, body)
                    cache.edges.extend(
                        _comment_edges(comment_id, rel_path, issue_key, body)
                    )

        _rebuild_blocks(cache)
        _rebuild_derived_tables(cache, project_dir)

        now = datetime.now()
        cache.last_full_rebuild = now
        cache.last_incremental_update = now

        save_index(project_dir, cache)
        logger.info(
            "graph_cache: full rebuild complete (files=%d, edges=%d, duration=%dms)",
            len(cache.files),
            len(cache.edges),
            int((time.monotonic() - started) * 1000),
        )
        return cache


# ============================================================================
# Incremental update
# ============================================================================


def update_cache_for_file(project_dir: Path, rel_path: str) -> bool:
    """Update the cache to reflect the current state of one file.

    Handles four cases:
    1. File doesn't exist in cache and doesn't exist on disk → no-op
    2. File exists on disk but not in cache → add
    3. File exists in cache but not on disk → remove
    4. File exists in both → replace (remove old edges, add new)

    Returns True if any state changed.
    """
    kind = _classify(rel_path)
    if kind is None:
        return False

    with _index_lock(project_dir):
        cache = load_index(project_dir) or _empty_cache()

        had_file = rel_path in cache.files

        # Remove any edges this file had previously emitted.
        cache.edges = [e for e in cache.edges if e.source_file != rel_path]
        cache.files.pop(rel_path, None)

        abs_path = project_dir / rel_path
        if abs_path.exists():
            if kind == "issue":
                parsed_issue = _load_issue_file(project_dir, rel_path)
                if parsed_issue is not None:
                    issue, body = parsed_issue
                    cache.files[rel_path] = _fingerprint_issue(issue, abs_path, body)
                    cache.edges.extend(_issue_edges(issue, rel_path, body))
            elif kind == "node":
                parsed_node = _load_node_file(project_dir, rel_path)
                if parsed_node is not None:
                    node, body = parsed_node
                    cache.files[rel_path] = _fingerprint_node(node, abs_path, body)
                    cache.edges.extend(_node_edges(node, rel_path, body))
            elif kind == "session":
                parsed_sess = _load_session_file(project_dir, rel_path)
                if parsed_sess is not None:
                    issues, body = parsed_sess
                    sid = session_id_from_rel_path(rel_path)
                    if sid is not None:
                        cache.files[rel_path] = _fingerprint_session(abs_path, body)
                        cache.edges.extend(_session_edges(sid, rel_path, issues, body))
            elif kind == "comment":
                parsed_cmt = _load_comment_file(project_dir, rel_path)
                if parsed_cmt is not None:
                    issue_key, body = parsed_cmt
                    cid = comment_id_from_rel_path(rel_path)
                    if cid is not None:
                        cache.files[rel_path] = _fingerprint_comment(abs_path, body)
                        cache.edges.extend(
                            _comment_edges(cid, rel_path, issue_key, body)
                        )
        else:
            # File deleted. Nothing more to do beyond the pop above.
            if not had_file:
                return False

        _rebuild_blocks(cache)
        _rebuild_derived_tables(cache, project_dir)
        cache.last_incremental_update = datetime.now()

        save_index(project_dir, cache)
        return True


# ============================================================================
# Freshness dispatcher
# ============================================================================


def ensure_fresh(project_dir: Path) -> bool:
    """Make sure the cache reflects the current state of the filesystem.

    Decision tree:
    1. If `graph/index.yaml` is missing or version-mismatched → full rebuild
    2. Otherwise walk `issues/` and `nodes/` and compare file mtimes
       against the stored fingerprints:
       - For every file on disk whose mtime or sha is newer than the cache,
         run `update_cache_for_file`
       - For every file in the cache that no longer exists on disk, run
         `update_cache_for_file` (which handles the delete case)
    3. If no changes, return False

    Returns True if the cache was rebuilt (full or incremental) at least once.
    """
    existing = load_index(project_dir)
    if existing is None:
        logger.info("graph_cache: cache missing or corrupt, dispatching full rebuild")
        full_rebuild(project_dir)
        return True

    # Collect current files on disk
    current_files: set[str] = set()

    issues_root = paths.issues_dir(project_dir)
    if issues_root.is_dir():
        for idir in issues_root.iterdir():
            if not idir.is_dir() or idir.name.startswith("."):
                continue
            abs_path = idir / paths.ISSUE_FILENAME
            if abs_path.is_file():
                current_files.add(str(abs_path.relative_to(project_dir)))

    nodes_root = paths.nodes_dir(project_dir)
    if nodes_root.is_dir():
        for abs_path in nodes_root.glob("*.yaml"):
            current_files.add(str(abs_path.relative_to(project_dir)))

    # KUI-132 / A7: also track session and comment files.
    sessions_root = paths.sessions_dir(project_dir)
    if sessions_root.is_dir():
        for sdir in sessions_root.iterdir():
            if not sdir.is_dir() or sdir.name.startswith("."):
                continue
            abs_path = sdir / paths.SESSION_FILENAME
            if abs_path.is_file():
                current_files.add(str(abs_path.relative_to(project_dir)))

    if issues_root.is_dir():
        for idir in issues_root.iterdir():
            if not idir.is_dir() or idir.name.startswith("."):
                continue
            comments_root = idir / paths.COMMENTS_SUBDIR
            if not comments_root.is_dir():
                continue
            for abs_path in comments_root.glob("*.yaml"):
                current_files.add(str(abs_path.relative_to(project_dir)))

    # Decide incremental-vs-full upfront. update_cache_for_file rebuilds
    # the derived tables (by_name, by_type, referenced_by) on EVERY call,
    # which walks the whole cache and re-reads every node file from disk.
    # That's O(N) per file → O(N²) total for a bulk update. full_rebuild
    # does the same work once. For changes ≥ INCREMENTAL_BAILOUT we bail
    # out to a full rebuild, which is dramatically faster for bulk
    # additions/renames/imports and avoids long lock-holds that race with
    # other ensure_fresh callers (file watcher, validate-on-edit hook).

    new_or_changed: list[str] = []
    for rel in current_files:
        fp = existing.files.get(rel)
        if fp is None:
            new_or_changed.append(rel)
            continue
        try:
            disk_mtime = (project_dir / rel).stat().st_mtime
        except OSError:
            continue
        if disk_mtime > fp.mtime + 1e-6:
            new_or_changed.append(rel)

    deleted = set(existing.files.keys()) - current_files
    change_count = len(new_or_changed) + len(deleted)

    if change_count >= _INCREMENTAL_BAILOUT:
        logger.info(
            "graph_cache: %d changes detected (>= %d), running full rebuild",
            change_count,
            _INCREMENTAL_BAILOUT,
        )
        full_rebuild(project_dir)
        return True

    rebuilt = False

    # New or modified files (small-batch incremental path)
    for rel in new_or_changed:
        abs_path = project_dir / rel
        fp = existing.files.get(rel)
        if fp is None:
            update_cache_for_file(project_dir, rel)
            rebuilt = True
            continue
        # Re-check sha (mtime can change without content changing)
        disk_sha = _compute_file_sha(abs_path)
        if disk_sha != fp.sha:
            update_cache_for_file(project_dir, rel)
            rebuilt = True
        else:
            # Just refresh the mtime in place to avoid re-hashing next time.
            with _index_lock(project_dir):
                cache = load_index(project_dir) or _empty_cache()
                if rel in cache.files:
                    cache.files[rel].mtime = abs_path.stat().st_mtime
                    cache.last_incremental_update = datetime.now()
                    save_index(project_dir, cache)

    # Deleted files
    for rel in deleted:
        update_cache_for_file(project_dir, rel)
        rebuilt = True

    if rebuilt:
        logger.info("graph_cache: incremental update applied")
    else:
        logger.debug("graph_cache: ensure_fresh — no changes detected")

    return rebuilt


# ============================================================================
# Public re-exports
# ============================================================================


__all__ = [
    "CACHE_VERSION",
    "INDEX_REL_PATH",
    "LOCK_REL_PATH",
    "ensure_fresh",
    "full_rebuild",
    "issue_key_from_rel_path",
    "load_index",
    "node_id_from_rel_path",
    "save_index",
    "update_cache_for_file",
]
