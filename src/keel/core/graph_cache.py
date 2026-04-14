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

from keel.core import paths
from keel.core.parser import parse_frontmatter_body
from keel.core.reference_parser import extract_references
from keel.models.graph import FileFingerprint, GraphEdge, GraphIndex
from keel.models.issue import Issue
from keel.models.node import ConceptNode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Backwards-compatible aliases — prefer importing from `keel.core.paths`.
INDEX_REL_PATH = paths.GRAPH_CACHE
LOCK_REL_PATH = paths.GRAPH_LOCK
CACHE_VERSION = 2

ISSUES_PREFIX = f"{paths.ISSUES_DIR}/"
NODES_PREFIX = f"{paths.NODES_DIR}/"


# ============================================================================
# Locking
# ============================================================================


DEFAULT_LOCK_TIMEOUT_S = 10.0
LOCK_POLL_INTERVAL_S = 0.05


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
    """Return `"issue"`, `"node"`, or None for non-tracked files."""
    if rel_path.startswith(ISSUES_PREFIX) and rel_path.endswith(
        f"/{paths.ISSUE_FILENAME}"
    ):
        return "issue"
    if rel_path.startswith(NODES_PREFIX) and rel_path.endswith(".yaml"):
        return "node"
    return None


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

    # `referenced_by` is the inverse of all `references` and `blocked_by` edges.
    for edge in cache.edges:
        if edge.type in ("references", "blocked_by", "related"):
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

    rebuilt = False

    # New or modified files
    for rel in current_files:
        abs_path = project_dir / rel
        fp = existing.files.get(rel)
        if fp is None:
            update_cache_for_file(project_dir, rel)
            rebuilt = True
            continue
        try:
            disk_mtime = abs_path.stat().st_mtime
        except OSError:
            continue
        if disk_mtime > fp.mtime + 1e-6:
            # Double-check with sha — mtime can change without content
            # changing (e.g. `touch`). If sha matches, update mtime only.
            disk_sha = _compute_file_sha(abs_path)
            if disk_sha != fp.sha:
                update_cache_for_file(project_dir, rel)
                rebuilt = True
            else:
                # Just refresh the mtime in place to avoid re-hashing next time.
                with _index_lock(project_dir):
                    cache = load_index(project_dir) or _empty_cache()
                    if rel in cache.files:
                        cache.files[rel].mtime = disk_mtime
                        cache.last_incremental_update = datetime.now()
                        save_index(project_dir, cache)

    # Deleted files
    stale = set(existing.files.keys()) - current_files
    for rel in stale:
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
