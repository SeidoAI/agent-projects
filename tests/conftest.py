"""Shared pytest fixtures."""

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def fake_tmux_on_path(tmp_path, monkeypatch):
    """Install a fake tmux executable on PATH and return a handle to
    inspect captured args, pane text, session-existence, etc."""
    bin_dir = tmp_path / "tmuxbin"
    bin_dir.mkdir()
    src = Path(__file__).parent / "fixtures" / "fake_tmux.py"
    dst = bin_dir / "tmux"
    shutil.copy(src, dst)
    dst.chmod(0o755)

    log_path = tmp_path / "fake_tmux.log"
    has_dir = tmp_path / "fake_tmux_has"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_TMUX_LOG", str(log_path))
    monkeypatch.setenv("FAKE_TMUX_HAS", str(has_dir))
    monkeypatch.setenv("FAKE_TMUX_PANE_TEXT", "")

    class Handle:
        def __init__(self):
            self.log_path = log_path
            self.has_dir = has_dir

        def calls(self) -> list[list[str]]:
            if not log_path.exists():
                return []
            return [
                line.split()
                for line in log_path.read_text().splitlines()
                if line
            ]

        def set_pane_text(self, text: str) -> None:
            monkeypatch.setenv("FAKE_TMUX_PANE_TEXT", text)

        def mark_session_exists(self, name: str) -> None:
            has_dir.mkdir(parents=True, exist_ok=True)
            (has_dir / name).touch()

    return Handle()


@pytest.fixture
def tmp_path_project(tmp_path: Path) -> Path:
    """Create a minimal tripwire project with default manifest, return its path.

    Mirrors the minimum shape expected by validator and CLI: project.yaml,
    issues/, nodes/, sessions/, docs/, and a default manifest in
    templates/artifacts/manifest.yaml matching the shipping template.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (project_dir / sub).mkdir()
    templates = project_dir / "templates" / "artifacts"
    templates.mkdir(parents=True)
    # Minimal manifest — real one is tested separately. Matches v0.6a shape.
    templates.joinpath("manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "artifacts": [
                    {
                        "name": "plan",
                        "file": "plan.md",
                        "template": "plan.md.j2",
                        "produced_at": "planning",
                        "produced_by": "pm",
                        "owned_by": "pm",
                        "required": True,
                    },
                ]
            }
        )
    )
    return project_dir


@pytest.fixture
def save_test_issue():
    """Factory fixture: save a minimal valid Issue via `store.save_issue`."""

    def _factory(project_dir: Path, key: str, **kwargs: Any) -> None:
        from tripwire.core.store import save_issue
        from tripwire.models import Issue

        default_body = (
            "## Context\nWith [[user-model]] reference.\n"
            "\n## Implements\nREQ-1\n"
            "\n## Repo scope\n- SeidoAI/web-app-backend\n"
            "\n## Requirements\n- thing\n"
            "\n## Execution constraints\nIf ambiguous, stop and ask.\n"
            "\n## Acceptance criteria\n- [ ] thing\n"
            "\n## Test plan\n```\nuv run pytest\n```\n"
            "\n## Dependencies\nnone\n"
            "\n## Definition of Done\n- [ ] done\n"
        )
        fm: dict[str, Any] = {
            "id": key,
            "title": f"Test {key}",
            "status": "todo",
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "kind": "feat",
            "body": default_body,
        }
        fm.update(kwargs)
        save_issue(project_dir, Issue.model_validate(fm), update_cache=False)

    return _factory


@pytest.fixture
def save_test_session():
    """Factory fixture: save a minimal valid AgentSession via `session_store.save_session`."""

    def _factory(
        project_dir: Path, session_id: str, *, plan: bool = False, **kwargs: Any
    ) -> None:
        from tripwire.core import paths
        from tripwire.core.session_store import save_session
        from tripwire.models import AgentSession

        fm: dict[str, Any] = {
            "id": session_id,
            "name": "Test session",
            "agent": "backend-coder",
            "issues": [],
            "status": "planned",
            "repos": [],
        }
        fm.update(kwargs)
        save_session(project_dir, AgentSession.model_validate(fm))
        if plan:
            paths.session_plan_path(project_dir, session_id).write_text(
                "# Plan\n", encoding="utf-8"
            )

    return _factory


@pytest.fixture
def save_test_node():
    """Factory fixture: save a minimal valid ConceptNode via `node_store.save_node`."""

    def _factory(
        project_dir: Path,
        node_id: str,
        *,
        body: str = "Description.\n",
        **kwargs: Any,
    ) -> None:
        from tripwire.core.node_store import save_node
        from tripwire.models import ConceptNode

        fm: dict[str, Any] = {
            "id": node_id,
            "type": "model",
            "name": "User",
            "status": "active",
            "body": body,
        }
        fm.update(kwargs)
        save_node(project_dir, ConceptNode.model_validate(fm), update_cache=False)

    return _factory


@pytest.fixture
def write_handoff_yaml():
    """Factory fixture: write a minimal handoff.yaml for a session."""

    def _factory(
        project_dir: Path, session_id: str, *, branch: str = "feat/test"
    ) -> None:
        from datetime import datetime, timezone
        from uuid import uuid4

        from tripwire.core.handoff_store import save_handoff
        from tripwire.models.handoff import SessionHandoff

        h = SessionHandoff(
            uuid=uuid4(),
            session_id=session_id,
            handoff_at=datetime.now(tz=timezone.utc),
            handed_off_by="pm",
            branch=branch,
        )
        save_handoff(project_dir, h)

    return _factory


@pytest.fixture
def fresh_project():
    """Factory: create a minimal tripwire project directory.

    Writes plain YAML (no frontmatter) matching ProjectConfig shape.
    Used by workspace CLI tests that need a real project on disk.
    """

    def _factory(
        proj_dir: Path, *, name: str = "test", key_prefix: str = "TST"
    ) -> Path:
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "project.yaml").write_text(
            f"name: {name}\n"
            f"key_prefix: {key_prefix}\n"
            "next_issue_number: 1\n"
            "next_session_number: 1\n",
            encoding="utf-8",
        )
        for sub in ("issues", "nodes", "sessions", "docs"):
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)
        return proj_dir

    return _factory


@pytest.fixture
def fresh_workspace():
    """Factory: workspace directory with workspace.yaml + nodes/."""

    def _factory(ws_dir: Path, *, slug: str = "ws") -> Path:
        from datetime import datetime, timezone
        from uuid import uuid4

        from tripwire.core.paths import workspace_nodes_dir
        from tripwire.core.workspace_store import save_workspace
        from tripwire.models.workspace import Workspace

        ws_dir.mkdir(parents=True, exist_ok=True)
        workspace_nodes_dir(ws_dir).mkdir(parents=True, exist_ok=True)
        now = datetime.now(tz=timezone.utc)
        save_workspace(
            ws_dir,
            Workspace(
                uuid=uuid4(),
                name=slug,
                slug=slug,
                description="",
                schema_version=1,
                tripwire_version="0.6.0",
                created_at=now,
                updated_at=now,
            ),
        )
        return ws_dir

    return _factory


@pytest.fixture
def tmp_project_manifest(tmp_path: Path):
    """Factory creating a minimal project with a custom manifest for
    validator testing."""

    def _factory(artifacts: list[dict]) -> Path:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(
            "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
        )
        (project_dir / "issues").mkdir()
        (project_dir / "nodes").mkdir()
        (project_dir / "sessions").mkdir()
        templates = project_dir / "templates" / "artifacts"
        templates.mkdir(parents=True)
        (templates / "manifest.yaml").write_text(
            yaml.safe_dump({"artifacts": artifacts})
        )
        return project_dir

    return _factory
