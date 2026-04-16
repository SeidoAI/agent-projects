"""keel workspace copy: first-time import of workspace nodes into a project."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from keel.cli.workspace import workspace_cmd
from keel.core.paths import workspace_nodes_dir
from keel.core.workspace_store import save_workspace
from keel.models.workspace import Workspace


def _git_commit_all(repo: Path, message: str = "test commit") -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def workspace_with_node():
    """Factory: create a workspace with a committed canonical node."""

    def _factory(
        ws_dir: Path, node_id: str = "auth-system", description: str = "Original."
    ) -> str:
        ws_dir.mkdir(parents=True, exist_ok=True)
        workspace_nodes_dir(ws_dir).mkdir(parents=True, exist_ok=True)
        now = datetime.now(tz=timezone.utc)
        save_workspace(
            ws_dir,
            Workspace(
                uuid=uuid4(),
                name="Seido",
                slug="seido",
                description="",
                schema_version=1,
                keel_version="0.6.0",
                created_at=now,
                updated_at=now,
            ),
        )
        # Write a canonical node file directly (simulating a workspace manager
        # author) — origin/scope = workspace but workspace_sha is stamped
        # by pull/copy on the project side, so the canonical file omits it.
        (workspace_nodes_dir(ws_dir) / f"{node_id}.yaml").write_text(
            f"""---
uuid: 00000000-0000-0000-0000-000000000001
id: {node_id}
type: system
name: Auth System
description: {description}
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=ws_dir, check=True)
        return _git_commit_all(ws_dir, f"add {node_id}")

    return _factory


class TestWorkspaceCopy:
    def test_copies_workspace_node_into_project(
        self,
        tmp_path,
        workspace_with_node,
        fresh_project,
    ):
        ws_dir = tmp_path / "ws"
        head_sha = workspace_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        # Link project first so copy knows which workspace to read.
        link_result = runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        assert link_result.exit_code == 0, link_result.output

        result = runner.invoke(
            workspace_cmd,
            ["copy", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code == 0, result.output

        # Verify the node was copied with workspace metadata stamped.
        from keel.core.node_store import load_node

        node = load_node(proj_dir, "auth-system")
        assert node.origin == "workspace"
        assert node.scope == "workspace"
        assert node.workspace_sha == head_sha
        assert node.workspace_pulled_at is not None

    def test_rejects_node_not_in_workspace(
        self,
        tmp_path,
        workspace_with_node,
        fresh_project,
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        result = runner.invoke(
            workspace_cmd,
            ["copy", "nonexistent", "--project-dir", str(proj_dir)],
        )
        # Partial success: 0 of 1 copied. Exit 1.
        assert result.exit_code != 0
        assert "nonexistent" in result.output
        assert "not found" in result.output.lower()

    def test_refuses_when_node_exists_locally(
        self,
        tmp_path,
        workspace_with_node,
        fresh_project,
        save_test_node,
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        # Pre-create local node with same id.
        save_test_node(proj_dir, node_id="auth-system")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        result = runner.invoke(
            workspace_cmd,
            ["copy", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        assert "already exists" in result.output.lower()

    def test_rejects_when_project_not_linked(
        self,
        tmp_path,
        workspace_with_node,
        fresh_project,
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            ["copy", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        assert "not linked" in result.output.lower()
