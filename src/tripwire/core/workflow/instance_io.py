"""Generic dict-based loader/saver for workflow instances (v0.13.1).

Every workflow that declares an ``instance:`` block in ``workflow.yaml``
also declares ``storage_path``: the on-disk layout template for one
materialised instance (e.g. one session, one issue). This module reads
that contract and provides three generic operations:

- :func:`load_instance` — read the instance YAML by ``(workflow_id,
  instance_id)`` and return the parsed dict.
- :func:`save_instance` — atomically write a parsed dict back to disk.
- :func:`list_instances` — enumerate instance ids for a workflow by
  walking the declared ``storage_path`` glob.

The loader is shape-agnostic by design — it doesn't know about
``AgentSession`` or ``Issue``. Callers that want typed access continue
to use the model-specific helpers (``load_session``, ``load_issue``).
The executor and the per-instance shape validator only need the dict
form, which is what this module provides.

File-format handling
--------------------

The instance files come in two flavours:

- **Frontmatter+body** — sessions, issues, nodes, comments. The body is
  surfaced under the special key ``body`` so callers can access any
  field in a single dict.
- **Pure YAML** — project.yaml-style. Returned as parsed.

A pure-YAML file that doesn't start with a frontmatter delimiter is
read via ``yaml.safe_load``; anything else flows through
:func:`tripwire.core.parser.parse_frontmatter_body` and is merged into
a single dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.core import paths
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.schema import Workflow, WorkflowInstanceShape
from tripwire.ui.services._atomic_write import atomic_write_text

# Filenames that live inside instance-storage directories but are NOT
# instances themselves. ``nodes/tripwire-graph-index.yaml`` is the
# derived graph cache; its sibling ``.tripwire-graph-index.lock`` is
# a transient build lock. Five other scan sites already skip both
# (``node_store.iter_nodes``, ``validator/__init__._load_nodes``,
# ``graph/cache._classify`` x2, ``ui/services/project_service``);
# the generic instance lister did not, so concept-freshness's
# ``list_instances`` would pick up the cache file and fire shape-
# validator errors on every ``tripwire validate`` after a rebuild.
_NON_INSTANCE_FILENAMES = frozenset(
    {paths.GRAPH_INDEX_FILENAME, paths.GRAPH_INDEX_LOCK_FILENAME}
)


class WorkflowMissingInstanceBlockError(LookupError):
    """Raised when a workflow's ``instance:`` block is absent.

    v0.13.1 emits ``workflow/instance_missing`` (a warning) when this
    block is missing; the generic loader treats it as a hard
    precondition because there is no fallback for "where does this
    instance live on disk".
    """


class WorkflowNotFoundError(LookupError):
    """Raised when the requested workflow id is not declared in
    ``workflow.yaml``.
    """


class InstanceNotFoundError(FileNotFoundError):
    """Raised when an instance's storage file does not exist on disk."""


def _resolve_instance_shape(
    project_dir: Path,
    workflow_id: str,
    *,
    workflow: Workflow | None = None,
) -> tuple[Workflow, WorkflowInstanceShape]:
    """Return ``(workflow, instance_shape)`` for *workflow_id*.

    If *workflow* is provided the caller has already paid for parsing
    ``workflow.yaml``; we trust it and skip a redundant
    :func:`load_workflows` call. The id is still checked to honour the
    documented error contract: passing a mismatched ``(workflow_id,
    workflow)`` pair surfaces as :class:`WorkflowNotFoundError` rather
    than silently using the wrong shape.

    Raises :class:`WorkflowNotFoundError` if the workflow id is unknown
    and :class:`WorkflowMissingInstanceBlockError` if the workflow
    declares no ``instance:`` block.
    """
    if workflow is None:
        spec = load_workflows(project_dir)
        workflow = spec.workflows.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(
                f"workflow {workflow_id!r} is not declared in workflow.yaml"
            )
    elif workflow.id != workflow_id:
        # Caller passed a pre-resolved workflow that doesn't match the
        # id. Don't silently use the wrong shape.
        raise WorkflowNotFoundError(
            f"pre-resolved workflow has id {workflow.id!r}, "
            f"caller asked for {workflow_id!r}"
        )
    if workflow.instance is None:
        raise WorkflowMissingInstanceBlockError(
            f"workflow {workflow_id!r} has no `instance:` block — add "
            f"storage_path, status_field, status_enum to workflow.yaml "
            f"so instance_io can locate its instance files."
        )
    return workflow, workflow.instance


def _render_storage_path(
    project_dir: Path, shape: WorkflowInstanceShape, instance_id: str
) -> Path:
    """Render an instance file's absolute path from the declared template.

    The template is a literal string with ``{instance_id}`` substituted.
    Any other ``{placeholder}`` is treated as a hard error so a malformed
    template surfaces immediately rather than silently producing a
    nonsense path.
    """
    rendered = shape.storage_path.replace("{instance_id}", instance_id)
    # Surface any leftover ``{placeholder}`` so we don't silently produce
    # a literal path containing brace tokens. v0.13.1 only declares
    # ``{instance_id}``; future placeholders should be threaded through
    # this function explicitly.
    if "{" in rendered and "}" in rendered:
        # Allow a literal `{` only if it's escaped by another brace; the
        # simple substring check is overly strict in pathological cases
        # but those don't appear in practice.
        raise ValueError(
            f"storage_path template {shape.storage_path!r} contains an "
            f"unsupported placeholder; only {{instance_id}} is recognised"
        )
    return project_dir / rendered


def _parse_instance_text(text: str) -> dict[str, Any]:
    """Parse instance file text into a single dict.

    Frontmatter+body files surface the body under the ``body`` key so
    callers (the executor, the shape validator) can do simple key
    access. Pure-YAML files are returned as parsed.

    v0.13.2 follow-up: ALWAYS include a ``body`` key for frontmatter-
    shaped files, even when the body is empty. The previous behaviour
    omitted ``body`` when ``body == ""`` — that lost the "this file was
    frontmatter-delimited" signal, and ``_serialise_instance_data``
    then round-tripped it to pure-YAML on save (stripping the leading
    ``---`` delimiter). Issue files with empty bodies — common after
    fresh ``tripwire issue create`` — became unparseable on re-load.
    """
    stripped = text.lstrip()
    if stripped.startswith("---"):
        try:
            frontmatter, body = parse_frontmatter_body(text)
        except ParseError as exc:
            raise ValueError(f"Could not parse instance file: {exc}") from exc
        return {**frontmatter, "body": body}
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"instance file must parse to a YAML mapping, got {type(data).__name__}"
        )
    return data


def _serialise_instance_data(data: dict[str, Any]) -> str:
    """Serialise an instance dict back to its on-disk format.

    A ``body`` key signals frontmatter+body shape; everything else is
    written as the frontmatter and ``body`` becomes the Markdown half.
    Without a ``body`` key the data is dumped as a pure YAML mapping.
    """
    if "body" in data:
        body = data["body"]
        frontmatter = {k: v for k, v in data.items() if k != "body"}
        return serialize_frontmatter_body(
            frontmatter, body if isinstance(body, str) else ""
        )
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_instance(
    project_dir: Path,
    workflow_id: str,
    instance_id: str,
    *,
    workflow: Workflow | None = None,
) -> dict[str, Any]:
    """Read a workflow instance's YAML file per its declared storage_path.

    Resolves the workflow's ``instance.storage_path`` template,
    substitutes ``{instance_id}`` and reads the file. Returns the parsed
    dict — frontmatter+body files are flattened with the body surfaced
    under the ``body`` key.

    If *workflow* is provided the caller has already parsed
    ``workflow.yaml`` and we trust the pre-resolved object instead of
    re-reading the file. This is the hot path for the executor, which
    parses ``workflow.yaml`` once per transition and threads the result
    through load/save.

    Raises:
        WorkflowNotFoundError: workflow_id not declared in workflow.yaml.
        WorkflowMissingInstanceBlockError: workflow has no ``instance:`` block.
        InstanceNotFoundError: rendered storage path doesn't exist on disk.
        ValueError: file exists but failed to parse.
    """
    _, shape = _resolve_instance_shape(project_dir, workflow_id, workflow=workflow)
    path = _render_storage_path(project_dir, shape, instance_id)
    if not path.is_file():
        raise InstanceNotFoundError(
            f"instance {instance_id!r} for workflow {workflow_id!r} not found at {path}"
        )
    return _parse_instance_text(path.read_text(encoding="utf-8"))


def save_instance(
    project_dir: Path,
    workflow_id: str,
    instance_id: str,
    data: dict[str, Any],
    *,
    workflow: Workflow | None = None,
) -> None:
    """Atomically write a workflow instance's YAML.

    Creates parent directories as needed. Frontmatter+body shape is
    inferred from the presence of a ``body`` key in *data*: everything
    other than ``body`` becomes the frontmatter, ``body`` becomes the
    Markdown half. Without a ``body`` key the dict is dumped as pure
    YAML.

    If *workflow* is provided we skip the redundant
    :func:`load_workflows` resolution — see :func:`load_instance` for
    the rationale.

    Raises:
        WorkflowNotFoundError: workflow_id not declared in workflow.yaml.
        WorkflowMissingInstanceBlockError: workflow has no ``instance:`` block.
    """
    _, shape = _resolve_instance_shape(project_dir, workflow_id, workflow=workflow)
    path = _render_storage_path(project_dir, shape, instance_id)
    atomic_write_text(path, _serialise_instance_data(data))


def list_instances(
    project_dir: Path,
    workflow_id: str,
    *,
    workflow: Workflow | None = None,
) -> list[str]:
    """Enumerate instance ids for a workflow by walking the storage_path.

    The declared ``storage_path`` template (e.g.
    ``instances/sessions/{instance_id}/session.yaml``) is split at
    ``{instance_id}``: the prefix names the parent directory to scan and
    the suffix names the expected child path inside each instance dir.
    An instance is "present" iff the rendered file exists.

    If *workflow* is provided we skip the redundant
    :func:`load_workflows` resolution — see :func:`load_instance` for
    the rationale.

    Returns a sorted list of instance ids. An empty list is returned
    when the parent directory does not exist (a fresh project before
    any instance has been written).

    Raises:
        WorkflowNotFoundError: workflow_id not declared in workflow.yaml.
        WorkflowMissingInstanceBlockError: workflow has no ``instance:`` block.
        ValueError: storage_path doesn't contain ``{instance_id}``.
    """
    _, shape = _resolve_instance_shape(project_dir, workflow_id, workflow=workflow)
    template = shape.storage_path
    placeholder = "{instance_id}"
    if placeholder not in template:
        raise ValueError(
            f"storage_path {template!r} has no {{instance_id}} placeholder; "
            f"list_instances needs one to enumerate instances"
        )
    head, _, tail = template.partition(placeholder)
    # The prefix tells us where to look. Two cases:
    #   "instances/sessions/" + "{instance_id}" + "/session.yaml"
    #       → parent = instances/sessions, child = each subdir's name
    #   "instances/nodes/" + "{instance_id}" + ".yaml"
    #       → parent = instances/nodes, child = file's stem
    # Strip the trailing slash off the head so it names a directory.
    head_path = head.rstrip("/")
    parent_dir = project_dir / head_path if head_path else project_dir
    if not parent_dir.is_dir():
        return []

    out: list[str] = []
    for entry in parent_dir.iterdir():
        # Skip non-instance siblings that share the storage dir — the
        # graph cache and its lock live alongside concept nodes but are
        # derived/transient, not instances. See _NON_INSTANCE_FILENAMES.
        if entry.name in _NON_INSTANCE_FILENAMES:
            continue
        # Compute the candidate instance id from the entry name + tail
        # shape. The tail starts with either a "/" (subdir layout) or a
        # file-suffix (flat layout). Use both shapes uniformly: render
        # the path with the candidate id and check it exists.
        candidate = entry.name
        if tail.startswith("/"):
            # Subdir layout: entry is a directory whose name is the id.
            if not entry.is_dir():
                continue
            instance_id = candidate
        else:
            # Flat layout: entry is a file like "<id><tail>".
            if not entry.is_file():
                continue
            if not tail or not candidate.endswith(tail):
                # The "no tail" case (storage_path ends in placeholder)
                # treats the entire entry name as the id.
                if tail:
                    continue
                instance_id = candidate
            else:
                instance_id = candidate[: -len(tail)]
        if not instance_id:
            continue
        rendered = _render_storage_path(project_dir, shape, instance_id)
        if rendered.is_file():
            out.append(instance_id)
    return sorted(set(out))


__all__ = [
    "InstanceNotFoundError",
    "WorkflowMissingInstanceBlockError",
    "WorkflowNotFoundError",
    "list_instances",
    "load_instance",
    "save_instance",
]
