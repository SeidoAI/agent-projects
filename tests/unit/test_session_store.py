"""Unit tests for `core/session_store.py` (AgentSession CRUD)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tripwire.core.session_store import (
    delete_session,
    list_sessions,
    load_session,
    save_session,
    session_dir,
    session_exists,
    session_yaml_path,
)
from tripwire.models import AgentSession


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal project.yaml + empty sessions directory."""
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
    (tmp_path / "sessions").mkdir()
    return tmp_path


class TestPathHelpers:
    def test_session_dir_returns_directory_path(self, project_dir: Path) -> None:
        assert session_dir(project_dir, "api-endpoints") == (
            project_dir / "sessions" / "api-endpoints"
        )

    def test_session_yaml_path_nests_under_dir(self, project_dir: Path) -> None:
        assert session_yaml_path(project_dir, "api-endpoints") == (
            project_dir / "sessions" / "api-endpoints" / "session.yaml"
        )


class TestSaveAndLoad:
    def test_save_creates_directory_and_yaml(self, project_dir: Path) -> None:
        s = AgentSession(id="api-endpoints", name="x", agent="backend-coder")
        save_session(project_dir, s)
        assert (project_dir / "sessions" / "api-endpoints").is_dir()
        assert (project_dir / "sessions" / "api-endpoints" / "session.yaml").is_file()

    def test_save_then_load_round_trip(self, project_dir: Path) -> None:
        original = AgentSession(
            id="api-endpoints",
            name="Round trip test",
            agent="backend-coder",
            issues=["TST-1", "TST-2"],
        )
        save_session(project_dir, original)
        loaded = load_session(project_dir, "api-endpoints")
        assert loaded.id == original.id
        assert loaded.name == original.name
        assert loaded.issues == ["TST-1", "TST-2"]

    def test_load_missing_raises_file_not_found(self, project_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_session(project_dir, "does-not-exist")

    def test_session_exists_true_only_when_yaml_present(
        self, project_dir: Path
    ) -> None:
        assert not session_exists(project_dir, "nope")
        save_session(project_dir, AgentSession(id="s1", name="x", agent="a"))
        assert session_exists(project_dir, "s1")

    def test_session_exists_false_for_empty_directory(self, project_dir: Path) -> None:
        """Directory without session.yaml does NOT count as an existing session."""
        (project_dir / "sessions" / "orphan").mkdir()
        assert not session_exists(project_dir, "orphan")


class TestListSessions:
    def test_empty_when_no_sessions(self, project_dir: Path) -> None:
        assert list_sessions(project_dir) == []

    def test_finds_directory_sessions(self, project_dir: Path) -> None:
        save_session(project_dir, AgentSession(id="alpha", name="a", agent="a"))
        save_session(project_dir, AgentSession(id="beta", name="b", agent="a"))
        save_session(project_dir, AgentSession(id="gamma", name="g", agent="a"))
        result = list_sessions(project_dir)
        ids = sorted(s.id for s in result)
        assert ids == ["alpha", "beta", "gamma"]

    def test_ignores_flat_yaml_files(self, project_dir: Path) -> None:
        """A flat `sessions/<id>.yaml` (old layout) is not recognised."""
        (project_dir / "sessions" / "flat.yaml").write_text(
            "---\nid: flat\nname: x\nagent: a\nstatus: planned\n---\n",
            encoding="utf-8",
        )
        save_session(project_dir, AgentSession(id="proper", name="x", agent="a"))
        result = list_sessions(project_dir)
        ids = [s.id for s in result]
        assert ids == ["proper"]

    def test_ignores_directories_without_session_yaml(self, project_dir: Path) -> None:
        (project_dir / "sessions" / "orphan").mkdir()
        save_session(project_dir, AgentSession(id="proper", name="x", agent="a"))
        result = list_sessions(project_dir)
        assert [s.id for s in result] == ["proper"]

    def test_skips_dotfiles(self, project_dir: Path) -> None:
        (project_dir / "sessions" / ".hidden").mkdir()
        (project_dir / "sessions" / ".hidden" / "session.yaml").write_text(
            "---\nid: hidden\nname: x\nagent: a\n---\n", encoding="utf-8"
        )
        save_session(project_dir, AgentSession(id="visible", name="x", agent="a"))
        result = list_sessions(project_dir)
        assert [s.id for s in result] == ["visible"]


class TestDelete:
    def test_delete_removes_directory(self, project_dir: Path) -> None:
        save_session(project_dir, AgentSession(id="gone", name="x", agent="a"))
        (project_dir / "sessions" / "gone" / "plan.md").write_text("plan\n")
        delete_session(project_dir, "gone")
        assert not (project_dir / "sessions" / "gone").exists()

    def test_delete_missing_is_noop(self, project_dir: Path) -> None:
        delete_session(project_dir, "never-existed")
