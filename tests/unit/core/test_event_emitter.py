"""Tests for `tripwire.core.event_emitter`.

KUI-98 — see `docs/specs/2026-04-26-v08-handoff.md` §1.2 and §4.16 for the
on-disk layout and emission contract this module implements.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from tripwire.core.event_emitter import EventEmitter, FileEmitter, NullEmitter


def test_null_emitter_returns_empty_string_and_writes_nothing(tmp_path: Path) -> None:
    emitter = NullEmitter()
    result = emitter.emit("firings", {"session_id": "s1", "x": 1})
    assert result == ""
    # No directories created anywhere relative to tmp_path.
    assert not (tmp_path / ".tripwire").exists()


def test_null_emitter_satisfies_protocol() -> None:
    emitter: EventEmitter = NullEmitter()
    assert emitter.emit("firings", {"session_id": "s1"}) == ""


def test_file_emitter_satisfies_protocol(tmp_path: Path) -> None:
    emitter: EventEmitter = FileEmitter(tmp_path)
    path = emitter.emit("firings", {"session_id": "s1", "kind": "tripwire_fire"})
    assert path  # non-empty
    assert Path(path).is_file()


def test_file_emitter_writes_to_expected_layout(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    payload = {"session_id": "v0710-routing", "kind": "tripwire_fire", "x": 42}
    path_str = emitter.emit("firings", payload)
    path = Path(path_str)

    expected_dir = tmp_path / ".tripwire" / "events" / "firings" / "v0710-routing"
    assert path.parent == expected_dir
    assert path.name == "0001.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == payload


def test_file_emitter_monotonic_numbering_per_kind_sid(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    p1 = Path(emitter.emit("firings", {"session_id": "s1"}))
    p2 = Path(emitter.emit("firings", {"session_id": "s1"}))
    p3 = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert p1.name == "0001.json"
    assert p2.name == "0002.json"
    assert p3.name == "0003.json"


def test_file_emitter_numbering_independent_across_sids(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    a1 = Path(emitter.emit("firings", {"session_id": "alpha"}))
    b1 = Path(emitter.emit("firings", {"session_id": "beta"}))
    a2 = Path(emitter.emit("firings", {"session_id": "alpha"}))
    assert a1.name == "0001.json"
    assert b1.name == "0001.json"
    assert a2.name == "0002.json"


def test_file_emitter_numbering_independent_across_kinds(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    f1 = Path(emitter.emit("firings", {"session_id": "s1"}))
    v1 = Path(emitter.emit("validator_runs", {"session_id": "s1"}))
    f2 = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert f1.name == "0001.json"
    assert v1.name == "0001.json"
    assert f2.name == "0002.json"


def test_file_emitter_creates_project_dir_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "newproj"  # does not exist yet
    emitter = FileEmitter(target)
    path = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert path.is_file()
    assert (target / ".tripwire" / "events" / "firings" / "s1").is_dir()


def test_file_emitter_rejects_payload_without_session_id(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    with pytest.raises(ValueError, match="session_id"):
        emitter.emit("firings", {})
    with pytest.raises(ValueError, match="session_id"):
        emitter.emit("firings", {"session_id": ""})


def test_file_emitter_rejects_empty_kind(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    with pytest.raises(ValueError, match="kind"):
        emitter.emit("", {"session_id": "s1"})


def test_file_emitter_rejects_kind_with_path_separators(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    with pytest.raises(ValueError, match="kind"):
        emitter.emit("firings/../etc", {"session_id": "s1"})
    with pytest.raises(ValueError, match="session_id"):
        emitter.emit("firings", {"session_id": "../escape"})


def test_file_emitter_concurrent_threads_no_clobber(tmp_path: Path) -> None:
    emitter = FileEmitter(tmp_path)
    n_threads = 8
    per_thread = 5
    barrier = threading.Barrier(n_threads)
    paths: list[str] = []
    paths_lock = threading.Lock()

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(per_thread):
            p = emitter.emit("firings", {"session_id": "s1", "thread": i, "n": j})
            with paths_lock:
                paths.append(p)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected_count = n_threads * per_thread
    assert len(paths) == expected_count
    assert len(set(paths)) == expected_count, "duplicate paths returned to callers"

    files = sorted(
        (tmp_path / ".tripwire" / "events" / "firings" / "s1").glob("*.json")
    )
    assert len(files) == expected_count
    names = [f.name for f in files]
    assert names == [f"{i:04d}.json" for i in range(1, expected_count + 1)]
    # Every file is valid JSON.
    for f in files:
        json.loads(f.read_text(encoding="utf-8"))


def test_file_emitter_pads_to_four_digits_then_grows(tmp_path: Path) -> None:
    """`<n>` is padded to at least 4 digits; rolls over correctly past 9999."""
    emitter = FileEmitter(tmp_path)
    # Pre-seed 9999 so the next emit lands on 10000.
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
    sid_dir.mkdir(parents=True)
    (sid_dir / "9999.json").write_text("{}", encoding="utf-8")
    p = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert p.name == "10000.json"


def test_file_emitter_resumes_numbering_from_existing_files(tmp_path: Path) -> None:
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
    sid_dir.mkdir(parents=True)
    (sid_dir / "0001.json").write_text("{}", encoding="utf-8")
    (sid_dir / "0007.json").write_text("{}", encoding="utf-8")
    emitter = FileEmitter(tmp_path)
    p = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert p.name == "0008.json"


def test_file_emitter_ignores_non_event_files_when_numbering(tmp_path: Path) -> None:
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
    sid_dir.mkdir(parents=True)
    (sid_dir / "README.md").write_text("notes", encoding="utf-8")
    (sid_dir / "0002.json.tmp").write_text("{}", encoding="utf-8")
    (sid_dir / "abc.json").write_text("{}", encoding="utf-8")
    emitter = FileEmitter(tmp_path)
    p = Path(emitter.emit("firings", {"session_id": "s1"}))
    assert p.name == "0001.json"
