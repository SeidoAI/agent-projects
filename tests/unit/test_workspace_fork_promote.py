"""keel workspace fork + promote."""

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
def workspace_with_auth(fresh_workspace):
    def _factory(ws_dir: Path) -> str:
        fresh_workspace(ws_dir, slug="ws")
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
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
        return _git_commit_all(ws_dir, "add auth-system")

    return _factory


class TestFork:
    def test_fork_flips_scope_to_local(
        self, tmp_path, workspace_with_auth, fresh_project
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir)
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd, ["copy", "auth-system", "--project-dir", str(proj_dir)]
        )

        result = runner.invoke(
            workspace_cmd,
            ["fork", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code == 0, result.output

        from keel.core.node_store import load_node

        node = load_node(proj_dir, "auth-system")
        assert node.origin == "workspace"  # preserved for audit
        assert node.scope == "local"  # flipped
        assert node.workspace_sha is not None  # kept

    def test_fork_rejects_local_origin_node(
        self, tmp_path, fresh_workspace, fresh_project, save_test_node
    ):
        ws_dir = tmp_path / "ws"
        fresh_workspace(ws_dir, slug="ws")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        save_test_node(proj_dir, node_id="local-only")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )

        result = runner.invoke(
            workspace_cmd,
            ["fork", "local-only", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        assert (
            "local" in result.output.lower()
            or "nothing to fork" in result.output.lower()
        )

    def test_fork_idempotent_on_already_forked(
        self, tmp_path, workspace_with_auth, fresh_project
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir)
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd, ["copy", "auth-system", "--project-dir", str(proj_dir)]
        )
        runner.invoke(
            workspace_cmd, ["fork", "auth-system", "--project-dir", str(proj_dir)]
        )

        # Second fork should be a no-op success.
        result = runner.invoke(
            workspace_cmd,
            ["fork", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code == 0, result.output
        assert "already" in result.output.lower() or "forked" in result.output.lower()


class TestPromote:
    def test_promote_pushes_local_node(
        self, tmp_path, fresh_workspace, fresh_project, save_test_node
    ):
        ws_dir = tmp_path / "ws"
        fresh_workspace(ws_dir, slug="ws")
        # Initialize git in workspace (fresh_workspace doesn't).
        subprocess.run(["git", "init", "-q"], cwd=ws_dir, check=True)
        # Need at least one commit for rev-parse HEAD to work — make an empty
        # placeholder commit.
        (ws_dir / ".gitkeep").write_text("", encoding="utf-8")
        _git_commit_all(ws_dir, "init")

        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        save_test_node(proj_dir, node_id="webhook-handler")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )

        result = runner.invoke(
            workspace_cmd,
            ["promote", "webhook-handler", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code == 0, result.output

        # Workspace should now have the node; project copy should now be workspace-origin.
        assert (workspace_nodes_dir(ws_dir) / "webhook-handler.yaml").is_file()

        from keel.core.node_store import load_node

        node = load_node(proj_dir, "webhook-handler")
        assert node.origin == "workspace"
        assert node.scope == "workspace"
        assert node.workspace_sha is not None

    def test_promote_rejects_on_collision(
        self, tmp_path, workspace_with_auth, fresh_project, save_test_node
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir)
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        save_test_node(proj_dir, node_id="auth-system")  # collides

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )

        result = runner.invoke(
            workspace_cmd,
            ["promote", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0, result.output

    def test_promote_rejects_workspace_origin_node(
        self, tmp_path, workspace_with_auth, fresh_project
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir)
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd, ["copy", "auth-system", "--project-dir", str(proj_dir)]
        )

        result = runner.invoke(
            workspace_cmd,
            ["promote", "auth-system", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        # Already workspace-origin — no-op / error.
        assert "workspace" in result.output.lower()
