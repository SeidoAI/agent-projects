"""Backward-compat shim: re-exports from `tripwire.core.graph.cache`.

Moved in v0.9 (KUI-131). New code should import from
`tripwire.core.graph.cache` directly. This module exists so that
existing call sites — `from tripwire.core.graph_cache import …` and
`from tripwire.core import graph_cache` — keep working.
"""

from __future__ import annotations

from tripwire.core.graph.cache import *  # noqa: F403
from tripwire.core.graph.cache import (  # noqa: F401
    CACHE_VERSION,
    COMMENTS_SUBDIR,
    INDEX_REL_PATH,
    ISSUES_PREFIX,
    LOCK_REL_PATH,
    NODES_PREFIX,
    SESSIONS_PREFIX,
    _classify,
    _comment_edges,
    _compute_file_sha,
    _empty_cache,
    _fingerprint_comment,
    _fingerprint_issue,
    _fingerprint_node,
    _fingerprint_session,
    _index_lock,
    _issue_edges,
    _load_comment_file,
    _load_issue_file,
    _load_node_file,
    _load_session_file,
    _node_edges,
    _rebuild_blocks,
    _rebuild_derived_tables,
    _session_edges,
    comment_id_from_rel_path,
    ensure_fresh,
    full_rebuild,
    issue_key_from_rel_path,
    load_index,
    node_id_from_rel_path,
    save_index,
    session_id_from_rel_path,
    update_cache_for_file,
)
