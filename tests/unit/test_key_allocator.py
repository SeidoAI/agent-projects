"""Unit tests for the atomic key allocator (file-locked next-key)."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from tripwire.core.key_allocator import KeyAllocationError, allocate_keys


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal project.yaml for the allocator to work against."""
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "test",
                "key_prefix": "TST",
                "next_issue_number": 1,
                "next_session_number": 1,
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_single_allocation(project_dir: Path) -> None:
    keys = allocate_keys(project_dir, "issue", count=1)
    assert keys == ["TST-1"]


def test_multiple_sequential_allocations(project_dir: Path) -> None:
    a = allocate_keys(project_dir, "issue", count=1)
    b = allocate_keys(project_dir, "issue", count=1)
    c = allocate_keys(project_dir, "issue", count=1)
    assert a == ["TST-1"]
    assert b == ["TST-2"]
    assert c == ["TST-3"]


def test_batch_allocation(project_dir: Path) -> None:
    keys = allocate_keys(project_dir, "issue", count=5)
    assert keys == ["TST-1", "TST-2", "TST-3", "TST-4", "TST-5"]
    # Counter advanced past the batch.
    next_keys = allocate_keys(project_dir, "issue", count=1)
    assert next_keys == ["TST-6"]


def test_counter_persisted_to_project_yaml(project_dir: Path) -> None:
    allocate_keys(project_dir, "issue", count=3)
    raw = yaml.safe_load((project_dir / "project.yaml").read_text())
    assert raw["next_issue_number"] == 4


def test_session_keys_use_session_counter(project_dir: Path) -> None:
    issue_a = allocate_keys(project_dir, "issue", count=1)
    session_a = allocate_keys(project_dir, "session", count=1)
    issue_b = allocate_keys(project_dir, "issue", count=1)
    session_b = allocate_keys(project_dir, "session", count=1)
    assert issue_a == ["TST-1"]
    assert issue_b == ["TST-2"]
    # Sessions get a different counter, so they start at 1 too.
    assert session_a[0].endswith("S1")
    assert session_b[0].endswith("S2")


def test_missing_project_yaml_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyAllocationError, match=r"project\.yaml not found"):
        allocate_keys(tmp_path, "issue")


def test_missing_key_prefix_raises(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump({"name": "test", "next_issue_number": 1})
    )
    with pytest.raises(KeyAllocationError, match="key_prefix"):
        allocate_keys(tmp_path, "issue")


def test_invalid_count_raises(project_dir: Path) -> None:
    with pytest.raises(ValueError, match="count must be"):
        allocate_keys(project_dir, "issue", count=0)
    with pytest.raises(ValueError, match="count must be"):
        allocate_keys(project_dir, "issue", count=-1)


def test_invalid_key_type_raises(project_dir: Path) -> None:
    with pytest.raises(ValueError, match="Unknown key_type"):
        allocate_keys(project_dir, "bogus")  # type: ignore[arg-type]


# ----------------------------------------------------------------------------
# Concurrent allocation — the critical test
# ----------------------------------------------------------------------------


def _allocate_one(project_dir_str: str) -> str:
    """Helper for ProcessPoolExecutor (must be top-level pickleable)."""
    return allocate_keys(Path(project_dir_str), "issue", count=1)[0]


def test_concurrent_threads_no_collisions(project_dir: Path) -> None:
    """10 threads, each calling allocate_keys, must produce 10 distinct keys."""
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(allocate_keys, project_dir, "issue", 1) for _ in range(10)]
        results = [f.result() for f in futures]

    flat = [k[0] for k in results]
    assert len(flat) == 10
    assert len(set(flat)) == 10  # all distinct
    # All keys should be in TST-1..TST-10 (no gaps, no collisions).
    expected = {f"TST-{i}" for i in range(1, 11)}
    assert set(flat) == expected


def test_concurrent_processes_no_collisions(project_dir: Path) -> None:
    """10 processes, each calling allocate_keys.

    This is the real concurrency test — different processes do not share
    Python's GIL or in-memory state, so they exercise the file lock for
    real. If `flock` doesn't work, this test will produce duplicates.
    """
    with ProcessPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_allocate_one, [str(project_dir)] * 10))

    assert len(results) == 10
    assert len(set(results)) == 10
    expected = {f"TST-{i}" for i in range(1, 11)}
    assert set(results) == expected


# ============================================================================
# Stale lock handling (Phase 2.3 of v0.5 architectural refactor)
# ============================================================================


class TestStaleLock:
    def test_acquires_over_stale_lock_file(self, project_dir: Path, caplog) -> None:
        """A lock file older than STALE_LOCK_AGE_S should not block
        acquisition — the advisory `flock` is released on process exit,
        so an old file left behind by a crashed process is cosmetic only.
        We expect a warning log entry."""
        import logging
        import os
        import time as _time

        from tripwire.core.locks import STALE_LOCK_AGE_S, project_lock

        # Create a "stale" lock file with an old mtime.
        lock_path = project_dir / ".tripwire.lock"
        lock_path.touch()
        old_mtime = _time.time() - (STALE_LOCK_AGE_S + 10)
        os.utime(lock_path, (old_mtime, old_mtime))

        caplog.set_level(logging.WARNING, logger="tripwire.core.locks")

        with project_lock(project_dir):
            pass  # Acquired without error.

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("Lock file" in r.getMessage() for r in warnings), (
            f"expected a stale-lock warning, got: {[r.getMessage() for r in warnings]}"
        )
