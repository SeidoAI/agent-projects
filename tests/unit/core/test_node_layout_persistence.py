"""Backward-parsing tests for the deprecated ConceptNode.layout field (KUI-104).

Concept Graph positions live in `.tripwire/concept-layout.json` — see
`tests/unit/core/test_concept_layout.py`. The `layout: {x, y}` key on
:class:`ConceptNode` is retained so node YAMLs written before the
sidecar migration still parse; this module pins that backward-compat
surface down. Nothing in the running app reads or writes the YAML field
after `core.concept_layout.bootstrap_from_yaml_if_absent` has run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.node_store import load_node, save_node
from tripwire.models import ConceptNode, NodeLayout


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "nodes").mkdir(parents=True)
    return tmp_path


def _node(node_id: str = "user-model", layout: NodeLayout | None = None) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        type="model",
        name="User",
        layout=layout,
    )


class TestNodeLayoutField:
    def test_default_layout_is_none(self) -> None:
        node = _node()
        assert node.layout is None

    def test_layout_round_trips_through_yaml(self, project_dir: Path) -> None:
        node = _node(layout=NodeLayout(x=120.5, y=-44.0))
        save_node(project_dir, node)
        loaded = load_node(project_dir, "user-model")
        assert loaded.layout is not None
        assert loaded.layout.x == pytest.approx(120.5)
        assert loaded.layout.y == pytest.approx(-44.0)

    def test_node_without_layout_round_trips(self, project_dir: Path) -> None:
        save_node(project_dir, _node())
        loaded = load_node(project_dir, "user-model")
        assert loaded.layout is None

    def test_layout_omitted_from_yaml_when_none(self, project_dir: Path) -> None:
        save_node(project_dir, _node())
        raw = (project_dir / "nodes" / "user-model.yaml").read_text()
        assert "layout:" not in raw

    def test_layout_rejects_non_numeric(self) -> None:
        with pytest.raises(ValueError):
            NodeLayout(x="bad", y=0.0)  # type: ignore[arg-type]
