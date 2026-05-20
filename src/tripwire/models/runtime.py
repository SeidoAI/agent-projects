"""Runtime configuration models.

Daemon-wide tunables for the monitor, queue runner, and PR watcher.
Shipped defaults live in ``templates/runtime/defaults.yaml``;
projects override via ``<project>/.tripwire/runtime/defaults.yaml``
or inline via ``project.yaml.runtime``.

Per the v0.14.0 "no hardcoded Python defaults" principle, models
declare structure only — no field defaults. A YAML missing any
required field raises ``ValidationError`` at
:func:`tripwire.core.runtime_config.load_resolved_runtime_config`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PushLoopConfig(BaseModel):
    """Push-loop tripwire thresholds.

    Both are integers because the runtime counts consecutive failed
    pushes as a discrete counter, not a duration. ``terminate_threshold``
    should be ``> warn_threshold`` so the warning fires first.
    """

    model_config = ConfigDict(extra="forbid")

    warn_threshold: int
    terminate_threshold: int


class MonitorConfig(BaseModel):
    """Runtime monitor thresholds.

    Stream-idle reaping detects silent agent death (wedged libuv after
    SIGSTOP/SIGCONT, ``claude -p`` post-``end_turn`` hangs). Max
    runtime is the hard wall-clock cap.
    """

    model_config = ConfigDict(extra="forbid")

    stream_idle_threshold_seconds: float
    max_runtime_seconds: float
    push_loop: PushLoopConfig


class QueueConfig(BaseModel):
    """Queue runner tunables — spend cap, concurrency, polling cadence."""

    model_config = ConfigDict(extra="forbid")

    cap_usd_per_window: float
    max_concurrent_spawns: int
    probe_interval_seconds: float
    tick_sleep_seconds: float


class PRWatcherConfig(BaseModel):
    """PR watcher daemon tunables."""

    model_config = ConfigDict(extra="forbid")

    poll_interval: float


class RuntimeDefaults(BaseModel):
    """Full resolved runtime configuration (shipped + project overrides)."""

    model_config = ConfigDict(extra="forbid")

    monitor: MonitorConfig
    queue: QueueConfig
    pr_watcher: PRWatcherConfig
