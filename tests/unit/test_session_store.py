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
    (tmp_path / "instances" / "sessions").mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestPathHelpers:
    def test_session_dir_returns_directory_path(self, project_dir: Path) -> None:
        assert session_dir(project_dir, "api-endpoints") == (
            project_dir / "instances" / "sessions" / "api-endpoints"
        )

    def test_session_yaml_path_nests_under_dir(self, project_dir: Path) -> None:
        assert session_yaml_path(project_dir, "api-endpoints") == (
            project_dir / "instances" / "sessions" / "api-endpoints" / "session.yaml"
        )


class TestSaveAndLoad:
    def test_save_creates_directory_and_yaml(self, project_dir: Path) -> None:
        s = AgentSession(id="api-endpoints", name="x", agent="backend-coder")
        save_session(project_dir, s)
        assert (project_dir / "instances" / "sessions" / "api-endpoints").is_dir()
        assert (
            project_dir / "instances" / "sessions" / "api-endpoints" / "session.yaml"
        ).is_file()

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

    def test_load_unknown_field_raises_session_load_error(
        self, project_dir: Path, tmp_path: Path
    ) -> None:
        """A session.yaml carrying a field outside the AgentSession
        schema (e.g. a stale name from before a rename) raises
        SessionLoadError, which wraps pydantic's ValidationError with
        a single migration instruction. The wrapper is name-blind —
        the offending field name is extracted from the pydantic error
        rather than known by load_session itself.
        """
        from tripwire.core.session_store import SessionLoadError

        sdir = project_dir / "instances" / "sessions" / "stale-shape"
        sdir.mkdir(parents=True)
        (sdir / "session.yaml").write_text(
            "---\n"
            "uuid: 11111111-1111-4111-8111-111111111111\n"
            "id: stale-shape\n"
            "name: Stale\n"
            "agent: backend-coder\n"
            "issues: []\n"
            "repos: []\n"
            "status: planned\n"
            "created_at: 2026-04-30T00:00:00Z\n"
            "updated_at: 2026-04-30T00:00:00Z\n"
            "current_station_instance: workflow:stale-shape:planned:1\n"
            "---\n",
            encoding="utf-8",
        )
        with pytest.raises(SessionLoadError) as excinfo:
            load_session(project_dir, "stale-shape")
        # Wrapper surfaces the offending field but the wrapper's code
        # never names it explicitly. Pydantic supplies the name.
        assert "current_station_instance" in str(excinfo.value)
        assert "re-spawn" in str(excinfo.value).lower()

    def test_session_exists_true_only_when_yaml_present(
        self, project_dir: Path
    ) -> None:
        assert not session_exists(project_dir, "nope")
        save_session(project_dir, AgentSession(id="s1", name="x", agent="a"))
        assert session_exists(project_dir, "s1")

    def test_session_exists_false_for_empty_directory(self, project_dir: Path) -> None:
        """Directory without session.yaml does NOT count as an existing session."""
        (project_dir / "instances" / "sessions" / "orphan").mkdir(
            parents=True, exist_ok=True
        )
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
        (project_dir / "instances" / "sessions" / "flat.yaml").write_text(
            "---\nid: flat\nname: x\nagent: a\nstatus: planned\n---\n",
            encoding="utf-8",
        )
        save_session(project_dir, AgentSession(id="proper", name="x", agent="a"))
        result = list_sessions(project_dir)
        ids = [s.id for s in result]
        assert ids == ["proper"]

    def test_ignores_directories_without_session_yaml(self, project_dir: Path) -> None:
        (project_dir / "instances" / "sessions" / "orphan").mkdir(
            parents=True, exist_ok=True
        )
        save_session(project_dir, AgentSession(id="proper", name="x", agent="a"))
        result = list_sessions(project_dir)
        assert [s.id for s in result] == ["proper"]

    def test_skips_dotfiles(self, project_dir: Path) -> None:
        (project_dir / "instances" / "sessions" / ".hidden").mkdir(
            parents=True, exist_ok=True
        )
        (
            project_dir / "instances" / "sessions" / ".hidden" / "session.yaml"
        ).write_text("---\nid: hidden\nname: x\nagent: a\n---\n", encoding="utf-8")
        save_session(project_dir, AgentSession(id="visible", name="x", agent="a"))
        result = list_sessions(project_dir)
        assert [s.id for s in result] == ["visible"]


class TestDelete:
    def test_delete_removes_directory(self, project_dir: Path) -> None:
        save_session(project_dir, AgentSession(id="gone", name="x", agent="a"))
        (project_dir / "instances" / "sessions" / "gone" / "plan.md").write_text(
            "plan\n"
        )
        delete_session(project_dir, "gone")
        assert not (project_dir / "instances" / "sessions" / "gone").exists()

    def test_delete_missing_is_noop(self, project_dir: Path) -> None:
        delete_session(project_dir, "never-existed")


class TestOutdatedSessionStatus:
    """`load_session` / `list_sessions` must intercept Pydantic's
    ValidationError when it fires on a pre-v0.9.4 ``status:`` value
    and surface a tight, actionable migration message instead.
    """

    def _write_outdated(self, project_dir: Path, sid: str, status: str) -> None:
        from tripwire.core.parser import serialize_frontmatter_body

        sdir = project_dir / "instances" / "sessions" / sid
        sdir.mkdir(parents=True, exist_ok=True)
        fm = {
            "uuid": "11111111-2222-4333-8444-555555555556",
            "id": sid,
            "name": "Outdated session",
            "agent": "backend-coder",
            "issues": [],
            "status": status,
            "repos": [],
        }
        text = serialize_frontmatter_body(fm, "")
        (sdir / "session.yaml").write_text(text, encoding="utf-8")

    def test_load_session_outdated_status_raises(self, project_dir: Path) -> None:
        from tripwire.core.session_store import OutdatedSessionStatusError

        self._write_outdated(project_dir, "sess-1", "active")
        with pytest.raises(OutdatedSessionStatusError) as exc_info:
            load_session(project_dir, "sess-1")
        assert exc_info.value.status == "active"
        assert "tripwire migrate status-values" in str(exc_info.value)

    def test_list_sessions_outdated_status_raises(self, project_dir: Path) -> None:
        from tripwire.core.session_store import OutdatedSessionStatusError

        self._write_outdated(project_dir, "sess-1", "waiting_for_review")
        with pytest.raises(OutdatedSessionStatusError):
            list_sessions(project_dir)
