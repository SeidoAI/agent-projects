"""Atomic next-key allocation under a file lock.

Used by `tripwire next-key` to allocate sequential issue/session keys
without races between concurrent invocations.

The lock file lives at `<project>/.tripwire.lock` and is acquired via
`fcntl.flock` (Unix). On contention, the call blocks until the lock is
released by the other process. Holding the lock is short — read a number,
increment it, write it back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

from tripwire.core import paths
from tripwire.core.id_generator import format_key
from tripwire.core.locks import DEFAULT_LOCK_TIMEOUT_S, LockTimeout, project_lock

# Backwards-compatible alias — prefer `tripwire.core.paths.PROJECT_LOCK`.
LOCK_FILENAME = paths.PROJECT_LOCK

KeyType = Literal["issue", "session"]
COUNTER_FIELD: dict[KeyType, str] = {
    "issue": "next_issue_number",
    "session": "next_session_number",
}


class KeyAllocationError(RuntimeError):
    """Raised when the next-key allocator cannot allocate a key."""


def allocate_keys(
    project_dir: Path,
    key_type: KeyType,
    count: int = 1,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> list[str]:
    """Atomically allocate `count` sequential keys of the given type.

    Reads `project.yaml`, increments the appropriate counter by `count`,
    writes `project.yaml` back, releases the lock. Returns the list of
    allocated keys (e.g. `["SEI-42", "SEI-43"]`).

    Raises:
        KeyAllocationError: if the lock cannot be acquired or `project.yaml`
            cannot be read/written.
        ValueError: if `count < 1` or `key_type` is invalid.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if key_type not in COUNTER_FIELD:
        raise ValueError(
            f"Unknown key_type {key_type!r}. Expected one of {list(COUNTER_FIELD)}."
        )

    project_yaml_path = paths.project_config_path(project_dir)
    if not project_yaml_path.exists():
        raise KeyAllocationError(
            f"project.yaml not found at {project_yaml_path}. Run `tripwire init` first."
        )

    counter_field = COUNTER_FIELD[key_type]

    try:
        with project_lock(project_dir, timeout_s=timeout_s):
            try:
                raw = (
                    yaml.safe_load(project_yaml_path.read_text(encoding="utf-8")) or {}
                )
            except yaml.YAMLError as exc:
                raise KeyAllocationError(
                    f"Could not parse {project_yaml_path}: {exc}"
                ) from exc

            if not isinstance(raw, dict):
                raise KeyAllocationError(
                    f"project.yaml must be a mapping, got {type(raw).__name__}"
                )

            prefix = raw.get("key_prefix")
            if not prefix:
                raise KeyAllocationError(
                    "project.yaml is missing required field `key_prefix`."
                )

            current = int(raw.get(counter_field, 1))
            allocated = list(range(current, current + count))
            raw[counter_field] = current + count

            project_yaml_path.write_text(
                yaml.safe_dump(raw, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
    except LockTimeout as exc:
        raise KeyAllocationError(str(exc)) from exc

    if key_type == "issue":
        return [format_key(prefix, n) for n in allocated]
    # Sessions are slug-based by default, but for symmetry we still produce
    # a `<PREFIX>-S<N>` form when called via the next-key allocator. The
    # `next-key --type session` CLI is mostly future-proofing; in v0 sessions
    # are slug-named (e.g. `api-endpoints-core`) and don't go through this path.
    return [f"{prefix}-S{n}" for n in allocated]
