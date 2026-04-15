"""keel init --workspace: link newly-initialized project to a workspace."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from keel.cli.init import init_cmd
from keel.core.paths import workspace_nodes_dir
from keel.core.store import load_project
from keel.core.workspace_store import load_workspace


def _init_args(target, **overrides):
    args = [
        str(target),
        "--name",
        overrides.get("name", "test-proj"),
        "--key-prefix",
        overrides.get("key_prefix", "TST"),
        "--base-branch",
        overrides.get("base_branch", "main"),
        "--non-interactive",
    ]
    if "workspace" in overrides:
        args.extend(["--workspace", str(overrides["workspace"])])
    if "copy_nodes" in overrides:
        args.extend(["--copy-nodes", overrides["copy_nodes"]])
    return args


def _git_commit_all(repo: Path, message: str = "init") -> str:
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
def workspace_with_node(fresh_workspace):
    def _factory(ws_dir: Path, node_id: str = "auth-system") -> str:
        fresh_workspace(ws_dir, slug="ws")
        (workspace_nodes_dir(ws_dir) / f"{node_id}.yaml").write_text(
            f"""---
uuid: 00000000-0000-0000-0000-000000000001
id: {node_id}
type: system
name: Auth System
description: Shared.
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


class TestInitStandaloneUnchanged:
    def test_init_without_workspace_flag(self, tmp_path):
        """Without --workspace, init works exactly as before (regression)."""
        runner = CliRunner()
        target = tmp_path / "p"
        result = runner.invoke(init_cmd, _init_args(target))
        assert result.exit_code == 0, result.output
        cfg = load_project(target)
        assert cfg.workspace is None


class TestInitWithWorkspace:
    def test_init_links_to_workspace(self, tmp_path, workspace_with_node):
        ws_dir = tmp_path / "ws"
        workspace_with_node(ws_dir)
        target = tmp_path / "p"

        runner = CliRunner()
        result = runner.invoke(init_cmd, _init_args(target, workspace=ws_dir))
        assert result.exit_code == 0, result.output

        cfg = load_project(target)
        assert cfg.workspace is not None

        ws = load_workspace(ws_dir)
        assert any(p.slug == "tst" for p in ws.projects)

    def test_init_with_copy_nodes(self, tmp_path, workspace_with_node):
        ws_dir = tmp_path / "ws"
        workspace_with_node(ws_dir, "auth-system")
        target = tmp_path / "p"

        runner = CliRunner()
        result = runner.invoke(
            init_cmd,
            _init_args(target, workspace=ws_dir, copy_nodes="auth-system"),
        )
        assert result.exit_code == 0, result.output

        from keel.core.node_store import list_nodes

        nodes = list_nodes(target)
        assert any(n.id == "auth-system" for n in nodes)

    def test_init_copy_nodes_requires_workspace(self, tmp_path):
        target = tmp_path / "p"
        runner = CliRunner()
        result = runner.invoke(init_cmd, _init_args(target, copy_nodes="auth-system"))
        assert result.exit_code != 0
        assert "workspace" in result.output.lower()
