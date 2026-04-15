"""keel workspace pull — trivial cases (no conflicts).

Conflict cases (merge briefs) are covered in test_workspace_pull_conflict
once T19 wires brief generation in.
"""

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

    def _factory(
        ws_dir: Path,
        node_id: str = "auth-system",
        description: str = "Original.",
    ) -> str:
        fresh_workspace(ws_dir, slug="ws")
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


class TestWorkspacePullTrivial:
    def test_pull_noop_when_nothing_to_sync(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """If no workspace-origin nodes in project, pull is a no-op."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        result = runner.invoke(
            workspace_cmd, ["pull", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output

    def test_pull_fast_forwards_unchanged_local(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """Workspace node evolves; project's copy is unchanged locally;
        pull fast-forwards the project's copy."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system", description="v1")
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

        # Update the workspace node.
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: v2
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        new_sha = _git_commit_all(ws_dir, "update auth-system to v2")

        # Pull.
        result = runner.invoke(
            workspace_cmd, ["pull", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output

        # Local copy should reflect v2 now, with workspace_sha bumped.
        from keel.core.node_store import load_node

        node = load_node(proj_dir, "auth-system")
        assert node.description == "v2"
        assert node.workspace_sha == new_sha

    def test_pull_skips_forked_nodes(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """A forked node (origin=workspace, scope=local) is skipped by pull."""
        ws_dir = tmp_path / "ws"
        workspace_repo_with_node(ws_dir, "auth-system", description="v1")
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

        # Fork the node (set scope=local).
        from keel.core.node_store import load_node, save_node

        node = load_node(proj_dir, "auth-system")
        forked = node.model_copy(update={"scope": "local"})
        save_node(proj_dir, forked, update_cache=False)

        # Update workspace node.
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: v2-upstream
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        _git_commit_all(ws_dir, "update")

        result = runner.invoke(
            workspace_cmd, ["pull", "--project-dir", str(proj_dir)]
        )
        assert result.exit_code == 0, result.output

        # Forked node unchanged.
        node = load_node(proj_dir, "auth-system")
        assert node.description == "v1"
        assert node.scope == "local"

    def test_pull_updates_workspace_yaml_last_pulled_sha(
        self, tmp_path, workspace_repo_with_node, fresh_project
    ):
        """After a successful pull, workspace.yaml's project entry
        should have last_pulled_sha updated."""
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

        # Update workspace.
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: updated
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        head_sha = _git_commit_all(ws_dir, "update")
        runner.invoke(
            workspace_cmd, ["pull", "--project-dir", str(proj_dir)]
        )

        from keel.core.workspace_store import load_workspace

        ws = load_workspace(ws_dir)
        entry = next(p for p in ws.projects if p.slug == "x")
        assert entry.last_pulled_sha == head_sha
