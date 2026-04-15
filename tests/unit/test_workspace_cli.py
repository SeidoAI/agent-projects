"""keel workspace CLI: init, link, unlink, list, status, prune."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from keel.cli.workspace import workspace_cmd
from keel.core.paths import workspace_nodes_dir
from keel.core.store import load_project as load_project_config
from keel.core.workspace_store import (
    load_workspace,
    save_workspace,
    workspace_exists,
)
from keel.models.workspace import Workspace


@pytest.fixture
def fresh_workspace():
    """Factory: create a workspace directory with workspace.yaml + nodes/."""

    def _factory(ws_dir: Path, slug: str = "ws") -> Path:
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
                keel_version="0.6.0",
                created_at=now,
                updated_at=now,
            ),
        )
        return ws_dir

    return _factory


@pytest.fixture
def fresh_project():
    """Factory: create a minimal keel project directory with project.yaml."""

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


class TestInit:
    def test_init_creates_manifest_and_nodes_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            [
                "init",
                "--name",
                "Seido",
                "--slug",
                "seido",
                "--workspace-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert workspace_exists(tmp_path)
        assert (tmp_path / "nodes").is_dir()
        ws = load_workspace(tmp_path)
        assert ws.name == "Seido"

    def test_init_refuses_if_workspace_exists(self, tmp_path):
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            [
                "init",
                "--name",
                "a",
                "--slug",
                "a",
                "--workspace-dir",
                str(tmp_path),
            ],
        )
        result2 = runner.invoke(
            workspace_cmd,
            [
                "init",
                "--name",
                "b",
                "--slug",
                "b",
                "--workspace-dir",
                str(tmp_path),
            ],
        )
        assert result2.exit_code != 0
        assert "already" in result2.output.lower()

    def test_init_initializes_git_repo(self, tmp_path):
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            [
                "init",
                "--name",
                "s",
                "--slug",
                "s",
                "--workspace-dir",
                str(tmp_path),
            ],
        )
        assert (tmp_path / ".git").is_dir()


class TestLink:
    def test_link_writes_both_sides(self, tmp_path, fresh_workspace, fresh_project):
        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        proj_dir = fresh_project(tmp_path / "proj", name="kb-pivot", key_prefix="KBP")

        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            [
                "link",
                str(ws_dir),
                "--project-dir",
                str(proj_dir),
                "--slug",
                "kbp",
            ],
        )
        assert result.exit_code == 0, result.output

        cfg = load_project_config(proj_dir)
        assert cfg.workspace is not None
        assert cfg.workspace.path

        ws = load_workspace(ws_dir)
        assert any(p.slug == "kbp" for p in ws.projects)

    def test_link_rejects_if_already_linked(
        self, tmp_path, fresh_workspace, fresh_project
    ):
        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            [
                "link",
                str(ws_dir),
                "--project-dir",
                str(proj_dir),
                "--slug",
                "x",
            ],
        )
        result = runner.invoke(
            workspace_cmd,
            [
                "link",
                str(ws_dir),
                "--project-dir",
                str(proj_dir),
                "--slug",
                "x",
            ],
        )
        assert result.exit_code != 0
        assert "already" in result.output.lower()


class TestUnlink:
    def test_unlink_clears_both_sides(
        self, tmp_path, fresh_workspace, fresh_project
    ):
        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )

        result = runner.invoke(
            workspace_cmd, ["unlink", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output
        assert load_project_config(proj_dir).workspace is None
        assert load_workspace(ws_dir).projects == []


class TestList:
    def test_list_empty(self, tmp_path, fresh_workspace):
        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd, ["list", "--workspace-dir", str(ws_dir)]
        )
        assert result.exit_code == 0
        assert "no projects" in result.output.lower()

    def test_list_registered_projects(
        self, tmp_path, fresh_workspace, fresh_project
    ):
        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        proj_dir = fresh_project(tmp_path / "proj", name="kb-pivot", key_prefix="KBP")
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            [
                "link",
                str(ws_dir),
                "--project-dir",
                str(proj_dir),
                "--slug",
                "kbp",
            ],
        )
        result = runner.invoke(
            workspace_cmd, ["list", "--workspace-dir", str(ws_dir)]
        )
        assert result.exit_code == 0
        assert "kb-pivot" in result.output
        assert "kbp" in result.output


class TestPrune:
    def test_prune_removes_orphans_with_force(
        self, tmp_path, fresh_workspace, fresh_project
    ):
        import shutil

        ws_dir = fresh_workspace(tmp_path / "ws", slug="seido")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        shutil.rmtree(proj_dir)

        dry = runner.invoke(
            workspace_cmd, ["prune", "--workspace-dir", str(ws_dir)]
        )
        assert "would remove" in dry.output.lower()
        assert len(load_workspace(ws_dir).projects) == 1

        forced = runner.invoke(
            workspace_cmd,
            ["prune", "--workspace-dir", str(ws_dir), "--force"],
        )
        assert forced.exit_code == 0
        assert load_workspace(ws_dir).projects == []
