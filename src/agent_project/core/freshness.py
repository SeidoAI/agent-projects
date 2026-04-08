"""Content hashing and staleness detection for concept nodes.

A concept node has an optional `source` pointing at a file (and optionally a
line range) in some repo, plus a `content_hash` recorded the last time the
node was rehashed. This module:

- Computes a SHA-256 hash of arbitrary content
- Fetches the content of a NodeSource from a local clone (preferred for
  speed) or via the GitHub API as a fallback (`gh api` subprocess)
- Compares the current hash against the stored one and reports the
  freshness status

The validator (`core/validator.py`) calls `check_node_freshness` once per
active node with a source. Network failures and missing files surface as
distinct statuses so the validator can produce actionable error messages.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import subprocess
from pathlib import Path

from agent_project.models.graph import FreshnessResult, FreshnessStatus
from agent_project.models.node import ConceptNode, NodeSource
from agent_project.models.project import ProjectConfig

logger = logging.getLogger(__name__)

HASH_PREFIX = "sha256:"


def hash_content(content: str | bytes) -> str:
    """Return a `sha256:<hex>` hash of the given content.

    Strings are encoded as UTF-8 before hashing so the hash is stable across
    platforms regardless of how the file was read.
    """
    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = content
    digest = hashlib.sha256(data).hexdigest()
    return f"{HASH_PREFIX}{digest}"


def _slice_lines(text: str, lines: tuple[int, int]) -> str:
    """Extract a 1-indexed inclusive line range from `text`.

    Mirrors the `source.lines: [start, end]` semantics from the node schema.
    Returns an empty string if the range falls entirely outside the file.
    """
    start, end = lines
    if start < 1 or end < start:
        raise ValueError(
            f"Invalid line range {lines}: must be 1-indexed and end >= start"
        )
    file_lines = text.splitlines()
    # Convert to 0-indexed half-open [start-1, end)
    return "\n".join(file_lines[start - 1 : end])


def _read_local(file_path: Path, lines: tuple[int, int] | None) -> str | None:
    """Read content from a local file, optionally extracting a line range.

    Returns None if the file does not exist.
    """
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    if lines is not None:
        return _slice_lines(text, lines)
    return text


def _fetch_github(
    repo: str,
    path: str,
    branch: str | None,
    lines: tuple[int, int] | None,
) -> str | None:
    """Fetch a file from GitHub via the `gh api` subprocess.

    Uses `gh api repos/<owner>/<repo>/contents/<path>?ref=<branch>` and
    decodes the base64-encoded content. Returns None if the call fails for
    any reason — the caller decides how to surface that as a freshness
    status.
    """
    api_path = f"repos/{repo}/contents/{path}"
    if branch:
        api_path = f"{api_path}?ref={branch}"
    try:
        result = subprocess.run(
            ["gh", "api", api_path],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # `gh` not installed
        return None
    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        return None
    try:
        # GitHub returns base64-encoded with embedded newlines.
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    if lines is not None:
        return _slice_lines(decoded, lines)
    return decoded


def fetch_content(source: NodeSource, project: ProjectConfig) -> str | None:
    """Fetch the current content of a NodeSource.

    Tries the local clone path from `project.repos[<repo>].local` first; if
    no local path is configured (or the file is missing locally), falls back
    to the GitHub API via `gh api`. Returns None if neither path yields
    content.
    """
    repo_entry = project.repos.get(source.repo)
    local_path = repo_entry.local if repo_entry is not None else None

    if local_path:
        expanded = Path(local_path).expanduser()
        if expanded.exists():
            logger.debug(
                "freshness: fetching %s:%s from local clone %s",
                source.repo,
                source.path,
                expanded,
            )
            content = _read_local(expanded / source.path, source.lines)
            if content is not None:
                return content
            logger.debug("freshness: local file missing, falling through to GitHub API")
            # File missing locally — fall through to GitHub API.

    logger.debug(
        "freshness: fetching %s:%s via gh api (branch=%s)",
        source.repo,
        source.path,
        source.branch,
    )
    return _fetch_github(source.repo, source.path, source.branch, source.lines)


def check_node_freshness(
    node: ConceptNode,
    project: ProjectConfig,
) -> FreshnessResult:
    """Compare a node's stored `content_hash` against the live content.

    Possible outcomes:
    - `NO_SOURCE`: node has no `source` field (e.g. planned nodes)
    - `SOURCE_MISSING`: source is set but the file cannot be fetched
    - `STALE`: content fetched, hash differs from stored
    - `FRESH`: content fetched, hash matches stored
    """
    if node.source is None:
        return FreshnessResult(
            node_id=node.id,
            status=FreshnessStatus.NO_SOURCE,
            detail="Node has no source field.",
        )

    content = fetch_content(node.source, project)
    if content is None:
        return FreshnessResult(
            node_id=node.id,
            status=FreshnessStatus.SOURCE_MISSING,
            detail=(
                f"Could not fetch {node.source.repo}:{node.source.path} "
                f"(branch={node.source.branch}). Check the local clone path "
                f"in project.yaml.repos or that `gh` is authenticated."
            ),
            stored_hash=node.source.content_hash,
        )

    current_hash = hash_content(content)
    stored_hash = node.source.content_hash

    if stored_hash is None:
        # No baseline to compare against — treat as stale and let the agent
        # rehash via `agent-project node update --rehash` (or auto-fix in a
        # later release).
        return FreshnessResult(
            node_id=node.id,
            status=FreshnessStatus.STALE,
            detail="Node has no stored content_hash to compare against.",
            current_hash=current_hash,
            stored_hash=None,
        )

    if current_hash == stored_hash:
        logger.debug("freshness: node %s is FRESH", node.id)
        return FreshnessResult(
            node_id=node.id,
            status=FreshnessStatus.FRESH,
            current_hash=current_hash,
            stored_hash=stored_hash,
        )

    logger.info(
        "freshness: node %s is STALE (current=%s, stored=%s)",
        node.id,
        current_hash[:24],
        stored_hash[:24],
    )
    return FreshnessResult(
        node_id=node.id,
        status=FreshnessStatus.STALE,
        detail=(
            f"Content hash mismatch: current={current_hash[:24]}…, "
            f"stored={stored_hash[:24]}…"
        ),
        current_hash=current_hash,
        stored_hash=stored_hash,
    )


def check_all_nodes(
    nodes: list[ConceptNode],
    project: ProjectConfig,
) -> list[FreshnessResult]:
    """Run freshness check across every active node with a source.

    Nodes with `status` other than `active` are skipped, as are nodes with
    no source (a planned node has nothing to check yet).
    """
    results: list[FreshnessResult] = []
    for node in nodes:
        if node.status != "active":
            continue
        if node.source is None:
            continue
        results.append(check_node_freshness(node, project))
    return results
