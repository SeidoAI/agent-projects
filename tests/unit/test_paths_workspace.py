"""Workspace path builders (v0.6b additions to paths.py)."""

from pathlib import Path

from keel.core import paths


def test_workspace_yaml_path():
    assert paths.workspace_yaml_path(Path("/ws")) == Path("/ws/workspace.yaml")


def test_workspace_nodes_dir():
    assert paths.workspace_nodes_dir(Path("/ws")) == Path("/ws/nodes")


def test_workspace_node_path():
    assert paths.workspace_node_path(Path("/ws"), "auth-system") == Path(
        "/ws/nodes/auth-system.yaml"
    )


def test_workspace_lock_path_reuses_project_lock_filename():
    assert paths.workspace_lock_path(Path("/ws")) == Path("/ws/.keel.lock")


def test_merge_briefs_dir():
    assert paths.merge_briefs_dir(Path("/proj")) == Path("/proj/.keel/merge-briefs")


def test_merge_brief_path():
    assert paths.merge_brief_path(Path("/proj"), "auth-system") == Path(
        "/proj/.keel/merge-briefs/auth-system.yaml"
    )


def test_constants():
    assert paths.WORKSPACE_YAML == "workspace.yaml"
    assert paths.WORKSPACE_NODES_DIR == "nodes"
    assert paths.MERGE_BRIEFS_DIR == ".keel/merge-briefs"
