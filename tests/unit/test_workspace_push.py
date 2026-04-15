"""keel workspace push — trivial cases (no upstream divergence)."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from keel.cli.workspace import workspace_cmd
from keel.core.paths import workspace_nodes_dir


def _git_commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
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
def workspace_repo_with_node(fresh_workspace):
    """Create a workspace repo with an initial committed node."""

    def _factory(ws_dir: Path, node_id: str = "auth-system") -> str:
        fresh_workspace(ws_dir, slug="ws")
        (workspace_nodes_dir(ws_dir) / f"{node_id}.yaml").write_text(
            f"""---
uuid: 00000000-0000-0000-0000-000000000001
id: {node_id}
type: system
name: Auth System
description: Original.
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


class TestWorkspacePushTrivial:
    def test_push_fast_forwards_modified_workspace_origin(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """Project modifies workspace-origin node; push fast-forwards upstream."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd,
            ["copy", "auth-system", "--project-dir", str(proj_dir)],
        )

        # Modify node locally.
        from keel.core.node_store import load_node, save_node

        node = load_node(proj_dir, "auth-system")
        save_node(
            proj_dir,
            node.model_copy(update={"description": "Project edit."}),
            update_cache=False,
        )

        result = runner.invoke(
            workspace_cmd, ["push", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output

        # Workspace repo should now reflect the edit.
        ws_yaml = (workspace_nodes_dir(ws_dir) / "auth-system.yaml").read_text()
        assert "Project edit" in ws_yaml

    def test_push_promotes_local_node_with_scope_workspace(
        self,
        tmp_path,
        workspace_repo_with_node,
        fresh_project,
        save_test_node,
    ):
        """A local-origin node with scope=workspace gets promoted on push."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )

        # Create a local node marked for promotion.
        save_test_node(proj_dir, node_id="webhook-handler", scope="workspace")

        result = runner.invoke(
            workspace_cmd, ["push", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output

        # Workspace should now have the new node.
        assert (workspace_nodes_dir(ws_dir) / "webhook-handler.yaml").is_file()

        # Project copy should now be origin=workspace with a workspace_sha stamp.
        from keel.core.node_store import load_node

        node = load_node(proj_dir, "webhook-handler")
        assert node.origin == "workspace"
        assert node.scope == "workspace"
        assert node.workspace_sha is not None

    def test_push_refuses_on_id_collision(
        self,
        tmp_path,
        workspace_repo_with_node,
        fresh_project,
        save_test_node,
    ):
        """Promote refuses if the workspace already has a node with that id."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        # Local node with same id as the already-existing workspace node.
        save_test_node(proj_dir, node_id="auth-system", scope="workspace")

        result = runner.invoke(
            workspace_cmd, ["push", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code != 0, result.output
        assert "collision" in result.output.lower() or "auth-system" in result.output

    def test_push_nothing_when_no_local_changes(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """Project with only unchanged workspace-origin nodes: nothing to push."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd,
            ["copy", "auth-system", "--project-dir", str(proj_dir)],
        )

        result = runner.invoke(
            workspace_cmd, ["push", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output
        assert "nothing to push" in result.output.lower()
