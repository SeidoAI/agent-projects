"""keel workspace merge-resolve: finalize an agent-resolved merge."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from keel.cli.workspace import workspace_cmd
from keel.core.merge_brief import (
    MergeType,
    build_merge_brief,
    list_pending_briefs,
    save_merge_brief,
)
from keel.core.paths import workspace_nodes_dir


def _git_commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", message],
        cwd=repo, check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def pull_produced_conflict(fresh_workspace, fresh_project):
    """Simulate a pull-conflict state: workspace has evolved, project has
    a local edit, brief has been written, draft merge lives in the node file.

    Returns (ws_dir, proj_dir, brief_node_id, workspace_head_sha).
    """

    def _factory(tmp_path: Path) -> tuple[Path, Path, str, str]:
        ws_dir = tmp_path / "ws"
        fresh_workspace(ws_dir, slug="ws")
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: v1
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
        _git_commit_all(ws_dir, "init")

        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(workspace_cmd,
                      ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"])
        runner.invoke(workspace_cmd,
                      ["copy", "auth-system", "--project-dir", str(proj_dir)])

        # Project edit.
        from keel.core.node_store import load_node, save_node
        node = load_node(proj_dir, "auth-system")
        save_node(proj_dir,
                  node.model_copy(update={"description": "Ours"}),
                  update_cache=False)

        # Workspace edit.
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: Theirs
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        head_sha = _git_commit_all(ws_dir, "upstream edit")

        # Run pull (will produce brief + draft).
        runner.invoke(workspace_cmd, ["pull", "--project-dir", str(proj_dir)])

        return ws_dir, proj_dir, "auth-system", head_sha

    return _factory


class TestMergeResolve:
    def test_resolve_deletes_brief_and_bumps_sha(
        self, tmp_path, pull_produced_conflict
    ):
        ws_dir, proj_dir, node_id, head_sha = pull_produced_conflict(tmp_path)

        # Simulate agent resolving: edit node file to a combined description.
        from keel.core.node_store import load_node, save_node
        node = load_node(proj_dir, node_id)
        resolved = node.model_copy(
            update={"description": "Combined: Ours + Theirs context."}
        )
        save_node(proj_dir, resolved, update_cache=False)

        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            ["merge-resolve", node_id, "--project-dir", str(proj_dir)],
        )
        assert result.exit_code == 0, result.output

        # Brief deleted.
        assert list_pending_briefs(proj_dir) == []

        # Node now has workspace_sha bumped.
        final = load_node(proj_dir, node_id)
        assert final.workspace_sha == head_sha

    def test_resolve_rejects_when_no_brief(self, tmp_path, fresh_project):
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        # No workspace to link to; also no brief.
        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            ["merge-resolve", "some-node", "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        assert "not linked" in result.output.lower() or "no pending" in result.output.lower()

    def test_resolve_keeps_brief_when_node_invalid(
        self, tmp_path, pull_produced_conflict
    ):
        ws_dir, proj_dir, node_id, _head = pull_produced_conflict(tmp_path)

        # Corrupt the node file so Pydantic validation fails on load.
        from keel.core.paths import node_path
        node_path(proj_dir, node_id).write_text(
            "---\n"
            "uuid: not-a-valid-uuid\n"
            "id: auth-system\n"
            "---\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            workspace_cmd,
            ["merge-resolve", node_id, "--project-dir", str(proj_dir)],
        )
        assert result.exit_code != 0
        # Brief preserved so agent can fix + retry.
        assert list_pending_briefs(proj_dir) == [node_id]
