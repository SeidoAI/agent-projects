"""tripwire workspace pull — conflict path writes merge briefs."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.workspace import workspace_cmd
from tripwire.core.merge_brief import load_merge_brief
from tripwire.core.paths import merge_brief_path, workspace_nodes_dir


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
    def _factory(ws_dir: Path, description: str = "v1") -> str:
        fresh_workspace(ws_dir, slug="ws")
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            f"""---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
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
        return _git_commit_all(ws_dir, "add auth-system")

    return _factory


class TestPullWritesBriefOnConflict:
    def test_pull_conflict_writes_brief(
        self, tmp_path, workspace_with_auth, fresh_project
    ):
        """Both sides modify the same field → brief written, exit 10."""
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir, description="v1")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd, ["copy", "auth-system", "--project-dir", str(proj_dir)]
        )

        # Project modifies description locally.
        from tripwire.core.node_store import load_node, save_node

        node = load_node(proj_dir, "auth-system")
        save_node(
            proj_dir,
            node.model_copy(update={"description": "Project edit"}),
            update_cache=False,
        )

        # Workspace modifies description with a different value, commits.
        (workspace_nodes_dir(ws_dir) / "auth-system.yaml").write_text(
            """---
uuid: 00000000-0000-0000-0000-000000000001
id: auth-system
type: system
name: Auth System
description: Upstream edit
status: active
origin: workspace
scope: workspace
related: []
tags: []
---
""",
            encoding="utf-8",
        )
        _git_commit_all(ws_dir, "update upstream")

        # Pull should detect conflict, write brief, exit 10.
        result = runner.invoke(workspace_cmd, ["pull", "--project-dir", str(proj_dir)])
        assert result.exit_code == 10, result.output

        # Brief file should exist with expected content.
        brief_path = merge_brief_path(proj_dir, "auth-system")
        assert brief_path.is_file()
        brief = load_merge_brief(proj_dir, "auth-system")
        assert brief is not None
        assert brief.node_id == "auth-system"
        by_field = {d.field: d.status for d in brief.field_diffs}
        assert by_field.get("description") == "conflict"

    def test_pull_conflict_applies_draft_to_node_file(
        self, tmp_path, workspace_with_auth, fresh_project
    ):
        """Draft merge keeps ours for conflict fields as a starting point."""
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir, description="v1")
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        runner.invoke(
            workspace_cmd, ["copy", "auth-system", "--project-dir", str(proj_dir)]
        )

        from tripwire.core.node_store import load_node, save_node

        node = load_node(proj_dir, "auth-system")
        save_node(
            proj_dir,
            node.model_copy(update={"description": "Ours"}),
            update_cache=False,
        )

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
        _git_commit_all(ws_dir, "upstream edit")

        runner.invoke(workspace_cmd, ["pull", "--project-dir", str(proj_dir)])

        # Draft keeps ours as the starting point.
        reloaded = load_node(proj_dir, "auth-system")
        assert reloaded.description == "Ours"
