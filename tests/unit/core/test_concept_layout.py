"""Unit tests for the Concept Graph layout sidecar.

The sidecar at `.tripwire/concept-layout.json` replaces the per-node
`layout: {x, y}` field that previously lived in node YAMLs (KUI-104).
This module covers the storage helper in isolation; the route-level half
lives in `tests/ui/routes/test_graph_routes.py::TestPatchConceptLayout`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripwire.core import paths
from tripwire.core.concept_layout import (
    SCHEMA_VERSION,
    bootstrap_from_yaml_if_absent,
    load_concept_layouts,
    merge_concept_layouts,
    save_concept_layouts,
)
from tripwire.core.node_store import save_node
from tripwire.models import ConceptNode, NodeLayout


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "nodes").mkdir(parents=True)
    return tmp_path


def _node(node_id: str, layout: NodeLayout | None = None) -> ConceptNode:
    return ConceptNode(id=node_id, type="model", name=node_id, layout=layout)


class TestSidecarLoad:
    def test_missing_file_returns_empty(self, project_dir: Path) -> None:
        assert load_concept_layouts(project_dir) == {}

    def test_corrupt_json_returns_empty(self, project_dir: Path) -> None:
        path = paths.concept_layout_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert load_concept_layouts(project_dir) == {}

    def test_version_mismatch_returns_empty(self, project_dir: Path) -> None:
        path = paths.concept_layout_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 999, "layouts": {"x": {"x": 1, "y": 2}}}),
            encoding="utf-8",
        )
        assert load_concept_layouts(project_dir) == {}

    def test_drops_entries_with_non_numeric_coords(self, project_dir: Path) -> None:
        path = paths.concept_layout_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": SCHEMA_VERSION,
                    "layouts": {
                        "good": {"x": 1.0, "y": 2.0},
                        "bad": {"x": "nope", "y": 0.0},
                    },
                }
            ),
            encoding="utf-8",
        )
        loaded = load_concept_layouts(project_dir)
        assert loaded == {"good": (1.0, 2.0)}


class TestSidecarSave:
    def test_save_then_load_round_trips(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.5, -2.5), "b": (0.0, 100.0)})
        loaded = load_concept_layouts(project_dir)
        assert loaded == {"a": (1.5, -2.5), "b": (0.0, 100.0)}

    def test_save_writes_under_dot_tripwire(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.0, 2.0)})
        assert (project_dir / ".tripwire" / "concept-layout.json").is_file()

    def test_save_creates_parent_dir(self, tmp_path: Path) -> None:
        # No `.tripwire/` exists yet; save_concept_layouts must mkdir it.
        save_concept_layouts(tmp_path, {"a": (1.0, 2.0)})
        assert (tmp_path / ".tripwire" / "concept-layout.json").is_file()

    def test_save_replaces_previous_contents(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.0, 2.0), "b": (3.0, 4.0)})
        save_concept_layouts(project_dir, {"a": (9.0, 9.0)})
        assert load_concept_layouts(project_dir) == {"a": (9.0, 9.0)}

    def test_no_partial_file_on_disk_after_write(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.0, 2.0)})
        # Tmp file from atomic write must not survive.
        assert not (project_dir / ".tripwire" / "concept-layout.json.tmp").exists()


class TestSidecarMerge:
    def test_merge_preserves_existing_entries(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.0, 2.0), "b": (3.0, 4.0)})
        merged = merge_concept_layouts(project_dir, {"c": (5.0, 6.0)})
        assert merged == {
            "a": (1.0, 2.0),
            "b": (3.0, 4.0),
            "c": (5.0, 6.0),
        }
        assert load_concept_layouts(project_dir) == merged

    def test_merge_overwrites_overlapping_entries(self, project_dir: Path) -> None:
        save_concept_layouts(project_dir, {"a": (1.0, 2.0)})
        merged = merge_concept_layouts(project_dir, {"a": (9.9, 9.9)})
        assert merged == {"a": (9.9, 9.9)}

    def test_merge_into_missing_sidecar_creates_one(self, project_dir: Path) -> None:
        merged = merge_concept_layouts(project_dir, {"a": (1.0, 2.0)})
        assert merged == {"a": (1.0, 2.0)}
        assert load_concept_layouts(project_dir) == merged


class TestBootstrapFromYaml:
    def test_lifts_layouts_from_node_yamls(self, project_dir: Path) -> None:
        save_node(project_dir, _node("alpha", layout=NodeLayout(x=10.0, y=20.0)))
        save_node(project_dir, _node("beta", layout=NodeLayout(x=-5.5, y=99.0)))
        save_node(project_dir, _node("gamma"))  # no layout — skipped

        bootstrap_from_yaml_if_absent(project_dir)

        loaded = load_concept_layouts(project_dir)
        assert loaded == {"alpha": (10.0, 20.0), "beta": (-5.5, 99.0)}

    def test_is_no_op_when_sidecar_already_exists(
        self, project_dir: Path
    ) -> None:
        # Sidecar present with a single entry; node YAML has its own
        # layout. Bootstrap must NOT clobber the sidecar.
        save_concept_layouts(project_dir, {"sidecar-blessed": (1.0, 2.0)})
        save_node(project_dir, _node("alpha", layout=NodeLayout(x=10.0, y=20.0)))

        bootstrap_from_yaml_if_absent(project_dir)

        assert load_concept_layouts(project_dir) == {"sidecar-blessed": (1.0, 2.0)}

    def test_creates_empty_sidecar_when_no_nodes_dir(self, tmp_path: Path) -> None:
        # No `nodes/` dir at all — bootstrap should still mark the
        # sidecar as initialised (empty) so subsequent calls short-circuit.
        bootstrap_from_yaml_if_absent(tmp_path)
        assert paths.concept_layout_path(tmp_path).is_file()
        assert load_concept_layouts(tmp_path) == {}

    def test_creates_empty_sidecar_when_no_node_has_layout(
        self, project_dir: Path
    ) -> None:
        save_node(project_dir, _node("alpha"))
        save_node(project_dir, _node("beta"))

        bootstrap_from_yaml_if_absent(project_dir)

        assert paths.concept_layout_path(project_dir).is_file()
        assert load_concept_layouts(project_dir) == {}
