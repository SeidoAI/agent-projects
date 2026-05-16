"""Unit tests for ``tripwire.core.workflow.instance_io`` (v0.13.1).

The generic dict-based instance loader reads a workflow's declared
``instance.storage_path`` template and provides load/save/list
operations independent of the entity's typed model.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tripwire.core.workflow.instance_io import (
    InstanceNotFoundError,
    WorkflowMissingInstanceBlockError,
    WorkflowNotFoundError,
    list_instances,
    load_instance,
    save_instance,
)


def _write_workflow(
    tmp_path: Path, storage_path: str, *, with_instance: bool = True
) -> None:
    """Write a minimal workflow.yaml with one workflow named ``demo``."""
    if with_instance:
        instance_block = dedent(
            f"""\
                instance:
                  storage_path: {storage_path}
                  status_field: status
                  status_enum: [planned, completed]
                  required_fields: [id, status]
            """
        )
    else:
        instance_block = ""
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflow_schema_version: 1
            workflows:
              demo:
                actor: pm-agent
                trigger: demo.start
                statuses:
                  - id: planned
                  - id: completed
                    terminal: true
                routes:
                  - id: planned-to-completed
                    actor: pm-agent
                    from: planned
                    to: completed
                    kind: forward
            """
        )
        # Indent the instance block under `demo:` (six spaces).
        .replace(
            "actor: pm-agent\n",
            "actor: pm-agent\n"
            + "".join(
                "    " + line + "\n" if line else ""
                for line in instance_block.splitlines()
            )
            if with_instance
            else "actor: pm-agent\n",
        ),
        encoding="utf-8",
    )


def _write_workflow_simple(
    tmp_path: Path,
    storage_path: str = "instances/demos/{instance_id}/demo.yaml",
    *,
    with_instance: bool = True,
) -> None:
    """A simpler workflow.yaml writer that builds the YAML by hand."""
    parts = [
        "workflow_schema_version: 1",
        "workflows:",
        "  demo:",
        "    actor: pm-agent",
        "    trigger: demo.start",
    ]
    if with_instance:
        parts.extend(
            [
                "    instance:",
                f"      storage_path: {storage_path}",
                "      status_field: status",
                "      status_enum: [planned, completed]",
                "      required_fields: [id, status]",
            ]
        )
    parts.extend(
        [
            "    statuses:",
            "      - id: planned",
            "      - id: completed",
            "        terminal: true",
            "    routes:",
            "      - id: planned-to-completed",
            "        actor: pm-agent",
            "        from: planned",
            "        to: completed",
            "        kind: forward",
        ]
    )
    (tmp_path / "workflow.yaml").write_text("\n".join(parts) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# load_instance / save_instance round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_save_then_load_returns_same_dict_pure_yaml(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        data = {"id": "d1", "status": "planned", "title": "first"}
        save_instance(tmp_path, "demo", "d1", data)
        # Pure-YAML round-trip: no body in the data, no body in the read.
        loaded = load_instance(tmp_path, "demo", "d1")
        assert loaded == data

    def test_save_then_load_returns_same_dict_with_body(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        data = {
            "id": "d2",
            "status": "planned",
            "body": "## Notes\n\nSome markdown body.\n",
        }
        save_instance(tmp_path, "demo", "d2", data)
        loaded = load_instance(tmp_path, "demo", "d2")
        # body trailing newline is preserved by serialize_frontmatter_body
        assert loaded["id"] == "d2"
        assert loaded["status"] == "planned"
        assert loaded["body"].strip() == data["body"].strip()

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        # `instances/demos/...` does not exist yet.
        assert not (tmp_path / "instances" / "demos").exists()
        save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})
        expected = tmp_path / "instances" / "demos" / "d1" / "demo.yaml"
        assert expected.is_file()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_load_raises_when_file_missing(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        with pytest.raises(InstanceNotFoundError):
            load_instance(tmp_path, "demo", "does-not-exist")

    def test_workflow_without_instance_block_raises(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path, with_instance=False)
        with pytest.raises(WorkflowMissingInstanceBlockError):
            load_instance(tmp_path, "demo", "d1")
        with pytest.raises(WorkflowMissingInstanceBlockError):
            save_instance(tmp_path, "demo", "d1", {"id": "d1"})
        with pytest.raises(WorkflowMissingInstanceBlockError):
            list_instances(tmp_path, "demo")

    def test_unknown_workflow_id_raises(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        with pytest.raises(WorkflowNotFoundError):
            load_instance(tmp_path, "no-such-workflow", "d1")


# ---------------------------------------------------------------------------
# list_instances
# ---------------------------------------------------------------------------


class TestListInstances:
    def test_empty_when_parent_dir_absent(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        assert list_instances(tmp_path, "demo") == []

    def test_lists_all_subdir_layout_instances(self, tmp_path: Path) -> None:
        _write_workflow_simple(tmp_path)
        for sid in ("alpha", "beta", "gamma"):
            save_instance(tmp_path, "demo", sid, {"id": sid, "status": "planned"})
        assert list_instances(tmp_path, "demo") == ["alpha", "beta", "gamma"]

    def test_lists_flat_layout_instances(self, tmp_path: Path) -> None:
        # Flat layout: storage_path ends with `<id>.yaml`, no subdir.
        _write_workflow_simple(
            tmp_path, storage_path="instances/flat/{instance_id}.yaml"
        )
        for sid in ("a", "b"):
            save_instance(tmp_path, "demo", sid, {"id": sid, "status": "planned"})
        assert list_instances(tmp_path, "demo") == ["a", "b"]

    def test_ignores_missing_inner_files(self, tmp_path: Path) -> None:
        """A directory under the parent with no inner file should not
        appear in the list — the rendered storage path must actually
        exist for the instance to count."""
        _write_workflow_simple(tmp_path)
        save_instance(tmp_path, "demo", "real", {"id": "real", "status": "planned"})
        # Stray subdir with no demo.yaml inside.
        (tmp_path / "instances" / "demos" / "stray").mkdir(parents=True)
        assert list_instances(tmp_path, "demo") == ["real"]

    def test_skips_graph_cache_in_flat_layout(self, tmp_path: Path) -> None:
        """Regression test for v0.13.2 #1.

        Flat-layout workflows (notably ``concept-freshness``) write to
        ``instances/nodes/<id>.yaml``. The graph cache
        ``tripwire-graph-index.yaml`` lives in the same directory; it
        is derived, not an instance. v0.13.1 picked it up via
        ``list_instances`` and fired three shape-validator errors per
        ``tripwire validate`` run. The five other node-dir scan sites
        already filtered it; ``list_instances`` did not.
        """
        from tripwire.core.paths import GRAPH_INDEX_FILENAME, GRAPH_INDEX_LOCK_FILENAME

        _write_workflow_simple(
            tmp_path, storage_path="instances/nodes/{instance_id}.yaml"
        )
        save_instance(
            tmp_path, "demo", "real-node", {"id": "real-node", "status": "planned"}
        )
        # Plant the graph cache + its lock alongside the real node.
        nodes_dir = tmp_path / "instances" / "nodes"
        (nodes_dir / GRAPH_INDEX_FILENAME).write_text(
            "cache: contents", encoding="utf-8"
        )
        (nodes_dir / GRAPH_INDEX_LOCK_FILENAME).write_text("", encoding="utf-8")
        assert list_instances(tmp_path, "demo") == ["real-node"]


# ---------------------------------------------------------------------------
# Pre-resolved workflow short-circuit (KUI: redundant-parse elimination)
# ---------------------------------------------------------------------------


class TestPreResolvedWorkflow:
    """The ``workflow=`` kwarg lets a caller pay for ``load_workflows``
    once and reuse the result. The executor uses this to avoid 3-5
    redundant ``workflow.yaml`` parses per transition.
    """

    def test_load_instance_with_pre_resolved_workflow_skips_load_workflows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_workflow_simple(tmp_path)
        save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})

        # Resolve the workflow once.
        from tripwire.core.workflow import instance_io as io_mod
        from tripwire.core.workflow.loader import load_workflows

        spec = load_workflows(tmp_path)
        workflow = spec.workflows["demo"]

        calls = {"n": 0}

        def _spy(project_dir):
            calls["n"] += 1
            return spec

        monkeypatch.setattr(io_mod, "load_workflows", _spy)

        # Threading the pre-resolved workflow should NOT call
        # load_workflows again.
        loaded = load_instance(tmp_path, "demo", "d1", workflow=workflow)
        assert loaded == {"id": "d1", "status": "planned"}
        assert calls["n"] == 0

    def test_save_instance_with_pre_resolved_workflow_skips_load_workflows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_workflow_simple(tmp_path)

        from tripwire.core.workflow import instance_io as io_mod
        from tripwire.core.workflow.loader import load_workflows

        spec = load_workflows(tmp_path)
        workflow = spec.workflows["demo"]

        calls = {"n": 0}

        def _spy(project_dir):
            calls["n"] += 1
            return spec

        monkeypatch.setattr(io_mod, "load_workflows", _spy)

        save_instance(
            tmp_path,
            "demo",
            "d1",
            {"id": "d1", "status": "planned"},
            workflow=workflow,
        )
        assert calls["n"] == 0
        # And the file was actually written.
        assert (tmp_path / "instances" / "demos" / "d1" / "demo.yaml").is_file()

    def test_list_instances_with_pre_resolved_workflow_skips_load_workflows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_workflow_simple(tmp_path)
        # Pre-seed an instance.
        save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})

        from tripwire.core.workflow import instance_io as io_mod
        from tripwire.core.workflow.loader import load_workflows

        spec = load_workflows(tmp_path)
        workflow = spec.workflows["demo"]

        calls = {"n": 0}

        def _spy(project_dir):
            calls["n"] += 1
            return spec

        monkeypatch.setattr(io_mod, "load_workflows", _spy)

        ids = list_instances(tmp_path, "demo", workflow=workflow)
        assert ids == ["d1"]
        assert calls["n"] == 0

    def test_load_instance_without_workflow_falls_back_to_resolve(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backwards compat: callers that don't pass ``workflow=`` hit
        the original resolve path (one ``load_workflows`` call)."""
        _write_workflow_simple(tmp_path)
        save_instance(tmp_path, "demo", "d1", {"id": "d1", "status": "planned"})

        from tripwire.core.workflow import instance_io as io_mod
        from tripwire.core.workflow.loader import load_workflows

        real_loader = load_workflows
        calls = {"n": 0}

        def _spy(project_dir):
            calls["n"] += 1
            return real_loader(project_dir)

        monkeypatch.setattr(io_mod, "load_workflows", _spy)

        loaded = load_instance(tmp_path, "demo", "d1")
        assert loaded == {"id": "d1", "status": "planned"}
        assert calls["n"] == 1

    def test_mismatched_pre_resolved_workflow_raises(self, tmp_path: Path) -> None:
        """Passing a workflow whose id doesn't match ``workflow_id`` is a
        caller bug — surface it loudly rather than silently using the
        wrong shape."""
        _write_workflow_simple(tmp_path)

        from tripwire.core.workflow.loader import load_workflows

        spec = load_workflows(tmp_path)
        workflow = spec.workflows["demo"]

        with pytest.raises(WorkflowNotFoundError):
            load_instance(tmp_path, "different-id", "d1", workflow=workflow)
