"""Batch spawn with cache priming (KUI-96 §E3).

PMs frequently launch N sessions in quick succession. They all share a
substantial prefix — the project's CLAUDE.md plus shipped skills — so
a single priming call ahead of the batch hydrates the prompt cache
and every following session reads from it on its first message.

The cache is server-side and ephemeral; ``claude -p`` already exposes
prompt caching automatically. The priming call is therefore a tiny
``claude -p`` invocation with the shared system content, sent once
before the first spawn. Batches of 1 skip priming — the no-op call
isn't free.

Tests inject ``prime_runner`` and ``spawn_runner`` so we don't actually
shell out to ``claude`` or run prep in a unit test. Manual smoke
verifies real cache_read behavior end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.batch_spawn import BatchSpawnReport, batch_spawn


def test_batch_spawn_calls_priming_once_before_first_spawn(tmp_path: Path) -> None:
    """One priming call runs first, then each spawn in order."""
    calls: list[tuple[str, str]] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append(("prime", system_content[:50]))
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append(("spawn", session_id))

    report = batch_spawn(
        tmp_path,
        ["s1", "s2", "s3"],
        prime=True,
        prime_runner=fake_prime,
        spawn_runner=fake_spawn,
        shared_system_content="hello shared world",
    )
    assert isinstance(report, BatchSpawnReport)
    # Priming is the first call; spawns follow in order.
    assert calls[0][0] == "prime"
    assert [c[1] for c in calls[1:]] == ["s1", "s2", "s3"]
    assert report.primed is True
    assert report.spawned == ["s1", "s2", "s3"]


def test_batch_spawn_skips_priming_for_single_session(tmp_path: Path) -> None:
    """Batches of 1 don't pay for priming."""
    calls: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append("prime")
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append(f"spawn:{session_id}")

    report = batch_spawn(
        tmp_path,
        ["s1"],
        prime=True,
        prime_runner=fake_prime,
        spawn_runner=fake_spawn,
        shared_system_content="x",
    )
    assert calls == ["spawn:s1"]
    assert report.primed is False
    assert report.spawned == ["s1"]


def test_batch_spawn_no_prime_flag_skips_priming(tmp_path: Path) -> None:
    """``prime=False`` opts out of the priming call entirely."""
    calls: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append("prime")
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append(f"spawn:{session_id}")

    batch_spawn(
        tmp_path,
        ["s1", "s2"],
        prime=False,
        prime_runner=fake_prime,
        spawn_runner=fake_spawn,
        shared_system_content="x",
    )
    assert calls == ["spawn:s1", "spawn:s2"]


def test_batch_spawn_records_failed_prime_but_still_spawns(tmp_path: Path) -> None:
    """Priming failure is non-fatal — the batch proceeds without it."""

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        return False  # priming failed

    spawned: list[str] = []

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        spawned.append(session_id)

    report = batch_spawn(
        tmp_path,
        ["s1", "s2"],
        prime=True,
        prime_runner=fake_prime,
        spawn_runner=fake_spawn,
        shared_system_content="x",
    )
    assert report.primed is False
    assert report.spawned == ["s1", "s2"]


def test_batch_spawn_resolves_default_shared_content_from_project(
    tmp_path: Path,
) -> None:
    """When no ``shared_system_content`` is passed, read CLAUDE.md."""
    (tmp_path / "CLAUDE.md").write_text("# project shared context\n\nlots of content\n")
    captured: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        captured.append(system_content)
        return True

    batch_spawn(
        tmp_path,
        ["s1", "s2"],
        prime=True,
        prime_runner=fake_prime,
        spawn_runner=lambda *a, **k: None,
    )
    assert captured
    assert "project shared context" in captured[0]


def test_batch_spawn_empty_session_list_is_a_noop(tmp_path: Path) -> None:
    """A batch with no sessions does nothing; the report shows it."""
    calls: list[str] = []

    def fake_prime(project_dir: Path, system_content: str) -> bool:
        calls.append("prime")
        return True

    def fake_spawn(project_dir: Path, session_id: str) -> None:
        calls.append("spawn")

    report = batch_spawn(
        tmp_path,
        [],
        prime=True,
        prime_runner=fake_prime,
        spawn_runner=fake_spawn,
        shared_system_content="x",
    )
    assert calls == []
    assert report.primed is False
    assert report.spawned == []
