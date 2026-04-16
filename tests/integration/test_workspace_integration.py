"""End-to-end workspace integration tests via subprocess CLI.

These exercise the full sync loop (create → link → copy → modify →
push → pull → resolve) as a user would from the shell, not through
in-process Click invocations. Slower but closer to the real thing.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

# ============================================================================
# Helpers
# ============================================================================


def _run_keel(
    cwd: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "keel", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _git_commit_all(repo: Path, message: str = "update") -> str:
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


def _bootstrap_workspace_with_node(
    tmp_path: Path,
    ws_name: str = "ws",
    node_id: str = "auth-system",
    description: str = "v1",
) -> Path:
    ws_dir = tmp_path / ws_name
    r = _run_keel(
        tmp_path,
        "workspace",
        "init",
        "--name",
        ws_name,
        "--slug",
        ws_name,
        "--workspace-dir",
        str(ws_dir),
    )
    assert r.returncode == 0, r.stdout + r.stderr

    (ws_dir / "nodes" / f"{node_id}.yaml").write_text(
        f"""---
uuid: 00000000-0000-0000-0000-000000000001
id: {node_id}
type: system
name: Shared Concept
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
    _git_commit_all(ws_dir, f"add {node_id}")
    return ws_dir


# ============================================================================
# T29: Create + link 2 projects
# ============================================================================


class TestCreateAndLinkTwoProjects:
    def test_create_workspace_and_two_projects(self, tmp_path):
        ws_dir = _bootstrap_workspace_with_node(tmp_path)

        for name, slug in [("proj-a", "pa"), ("proj-b", "pb")]:
            proj_dir = tmp_path / name
            r = _run_keel(
                tmp_path,
                "init",
                "--name",
                name,
                "--key-prefix",
                slug.upper(),
                "--non-interactive",
                "--workspace",
                str(ws_dir),
                str(proj_dir),
            )
            assert r.returncode == 0, r.stdout + r.stderr

        r = _run_keel(tmp_path, "workspace", "list", "--workspace-dir", str(ws_dir))
        assert "pa" in r.stdout
        assert "pb" in r.stdout


# ============================================================================
# T30: Sync happy path (A modifies, B pulls)
# ============================================================================


class TestSyncHappyPath:
    def test_project_a_modifies_b_pulls(self, tmp_path):
        ws_dir = _bootstrap_workspace_with_node(tmp_path, description="v1")

        for name, slug in [("proj-a", "PA"), ("proj-b", "PB")]:
            proj_dir = tmp_path / name
            r = _run_keel(
                tmp_path,
                "init",
                "--name",
                name,
                "--key-prefix",
                slug,
                "--non-interactive",
                "--workspace",
                str(ws_dir),
                "--copy-nodes",
                "auth-system",
                str(proj_dir),
            )
            assert r.returncode == 0, r.stdout + r.stderr

        proj_a = tmp_path / "proj-a"
        proj_b = tmp_path / "proj-b"

        # Project A edits the node locally.
        node_a_path = proj_a / "nodes" / "auth-system.yaml"
        text = node_a_path.read_text(encoding="utf-8")
        text = text.replace("description: v1", "description: A-edit")
        node_a_path.write_text(text, encoding="utf-8")

        # Project A pushes.
        r = _run_keel(proj_a, "workspace", "push")
        assert r.returncode == 0, r.stdout + r.stderr

        # Project B pulls.
        r = _run_keel(proj_b, "workspace", "pull")
        assert r.returncode == 0, r.stdout + r.stderr

        node_b_text = (proj_b / "nodes" / "auth-system.yaml").read_text(
            encoding="utf-8"
        )
        assert "A-edit" in node_b_text


# ============================================================================
# T31: Sync conflict resolved via merge-resolve
# ============================================================================


class TestSyncConflict:
    def test_conflict_produces_brief_and_resolves(self, tmp_path):
        ws_dir = _bootstrap_workspace_with_node(tmp_path, description="base")
        proj_a = tmp_path / "proj-a"
        proj_b = tmp_path / "proj-b"

        for name, slug, proj_dir in [
            ("proj-a", "PA", proj_a),
            ("proj-b", "PB", proj_b),
        ]:
            r = _run_keel(
                tmp_path,
                "init",
                "--name",
                name,
                "--key-prefix",
                slug,
                "--non-interactive",
                "--workspace",
                str(ws_dir),
                "--copy-nodes",
                "auth-system",
                str(proj_dir),
            )
            assert r.returncode == 0

        # Project A edits description and pushes.
        path_a = proj_a / "nodes" / "auth-system.yaml"
        path_a.write_text(
            path_a.read_text().replace("description: base", "description: A-text"),
            encoding="utf-8",
        )
        _run_keel(proj_a, "workspace", "push", check=True)

        # Project B edits description differently (without pulling first).
        path_b = proj_b / "nodes" / "auth-system.yaml"
        path_b.write_text(
            path_b.read_text().replace("description: base", "description: B-text"),
            encoding="utf-8",
        )

        # Project B pulls — should surface a conflict brief.
        r = _run_keel(proj_b, "workspace", "pull")
        assert r.returncode == 10, r.stdout + r.stderr
        brief_path = proj_b / ".keel" / "merge-briefs" / "auth-system.yaml"
        assert brief_path.is_file()

        # Simulate agent resolving: write a combined description.
        path_b.write_text(
            path_b.read_text().replace(
                "description: B-text", "description: Combined A+B"
            ),
            encoding="utf-8",
        )

        # Finalize.
        r = _run_keel(proj_b, "workspace", "merge-resolve", "auth-system")
        assert r.returncode == 0, r.stdout + r.stderr
        assert not brief_path.exists()


# ============================================================================
# T32: Standalone project unchanged (regression)
# ============================================================================


class TestStandaloneProjectUnchanged:
    def test_no_workspace_field_validates(self, tmp_path):
        """Project with no workspace pointer passes keel validate."""
        proj = tmp_path / "standalone"
        r = _run_keel(
            tmp_path,
            "init",
            "--name",
            "standalone",
            "--key-prefix",
            "SOL",
            "--non-interactive",
            str(proj),
        )
        assert r.returncode == 0

        r = _run_keel(proj, "validate", "--strict")
        # validate may emit quality-consistency warnings etc. — we only
        # care that it doesn't emit workspace/handoff-related errors.
        # exit 0 (clean) or 1 (warnings) both acceptable; exit 2 is not.
        assert r.returncode in (0, 1), r.stdout + r.stderr
        assert "handoff_schema" not in r.stdout
        assert "workspace_schema" not in r.stdout


# ============================================================================
# T33: Concurrent pushes
# ============================================================================


class TestConcurrentPushes:
    def test_parallel_push_no_lost_writes(self, tmp_path):
        """5 projects each promoting a distinct node, run in parallel.

        Because each node id is unique, no collisions occur. The workspace
        lock should serialize the pushes and all 5 nodes should land in
        the workspace.
        """
        ws_dir = _bootstrap_workspace_with_node(tmp_path, description="v1")

        # Create 5 projects, each with one unique promotion candidate.
        proj_dirs = []
        for i in range(5):
            name = f"proj-{i}"
            slug = f"P{i}"
            proj_dir = tmp_path / name
            r = _run_keel(
                tmp_path,
                "init",
                "--name",
                name,
                "--key-prefix",
                slug,
                "--non-interactive",
                "--workspace",
                str(ws_dir),
                str(proj_dir),
            )
            assert r.returncode == 0

            # Add a local scope=workspace node unique to this project.
            node_id = f"concept-{i}"
            (proj_dir / "nodes" / f"{node_id}.yaml").write_text(
                f"""---
uuid: 00000000-0000-0000-0000-00000000000{i}
id: {node_id}
type: concept
name: Concept {i}
description: Local.
status: active
origin: local
scope: workspace
related: []
tags: []
---
""",
                encoding="utf-8",
            )
            proj_dirs.append(proj_dir)

        # Launch all pushes in parallel threads.
        results: list[subprocess.CompletedProcess] = [None] * 5  # type: ignore[list-item]

        def _do_push(i: int):
            results[i] = _run_keel(proj_dirs[i], "workspace", "push")

        threads = [threading.Thread(target=_do_push, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i, r in enumerate(results):
            assert r.returncode == 0, f"proj-{i} push failed: {r.stdout}\n{r.stderr}"

        # All 5 nodes should now be in the workspace.
        for i in range(5):
            assert (ws_dir / "nodes" / f"concept-{i}.yaml").is_file()
