"""Workspace-aware lint rules (v0.6b)."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tripwire.cli.workspace import workspace_cmd
from tripwire.core import lint_rules  # noqa: F401 — registers rules
from tripwire.core.linter import Linter
from tripwire.core.paths import merge_briefs_dir, workspace_nodes_dir


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
def workspace_with_auth(fresh_workspace):
    def _factory(ws_dir: Path) -> str:
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
        return _git_commit_all(ws_dir, "add")

    return _factory


class TestStaleWorkspaceNodes:
    def test_flags_node_behind_head(self, tmp_path, workspace_with_auth, fresh_project):
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

        # Advance the workspace by making a new commit.
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
        _git_commit_all(ws_dir, "bump")

        linter = Linter(project_dir=proj_dir)
        findings = list(linter.run_stage("scoping"))
        assert any(f.code == "lint/stale_workspace_nodes" for f in findings)

    def test_no_finding_when_not_linked(self, fresh_project, tmp_path):
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")
        linter = Linter(project_dir=proj_dir)
        findings = list(linter.run_stage("scoping"))
        assert not any(f.code == "lint/stale_workspace_nodes" for f in findings)


class TestUnresolvedMergeBriefs:
    def test_error_at_handoff_with_pending_brief(self, tmp_path_project):
        briefs = merge_briefs_dir(tmp_path_project)
        briefs.mkdir(parents=True)
        (briefs / "auth-system.yaml").write_text(
            "node_id: auth-system\n", encoding="utf-8"
        )
        linter = Linter(project_dir=tmp_path_project)
        findings = list(linter.run_stage("handoff"))
        assert any(
            f.code == "lint/unresolved_merge_briefs" and f.severity == "error"
            for f in findings
        )

    def test_no_finding_when_no_briefs(self, tmp_path_project):
        linter = Linter(project_dir=tmp_path_project)
        findings = list(linter.run_stage("handoff"))
        assert not any(f.code == "lint/unresolved_merge_briefs" for f in findings)


class TestUnpushedPromotionsBump:
    def test_info_without_workspace(self, save_test_node, tmp_path_project):
        save_test_node(
            tmp_path_project,
            node_id="local-concept",
            origin="local",
            scope="workspace",
        )
        linter = Linter(project_dir=tmp_path_project)
        findings = [
            f
            for f in linter.run_stage("scoping")
            if f.code == "lint/unpushed_promotion_candidates"
        ]
        assert len(findings) == 1
        assert findings[0].severity == "info"

    def test_warning_with_workspace(
        self, tmp_path, workspace_with_auth, fresh_project, save_test_node
    ):
        ws_dir = tmp_path / "ws"
        workspace_with_auth(ws_dir)
        proj_dir = fresh_project(tmp_path / "proj", name="x", key_prefix="X")

        runner = CliRunner()
        runner.invoke(
            workspace_cmd,
            ["link", str(ws_dir), "--project-dir", str(proj_dir), "--slug", "x"],
        )
        save_test_node(
            proj_dir,
            node_id="local-concept",
            origin="local",
            scope="workspace",
        )

        linter = Linter(project_dir=proj_dir)
        findings = [
            f
            for f in linter.run_stage("scoping")
            if f.code == "lint/unpushed_promotion_candidates"
        ]
        assert len(findings) == 1
        assert findings[0].severity == "warning"
