"""Heuristic registry: ids and check-code mapping."""

from __future__ import annotations

from tripwire._internal.heuristics import (
    heuristic_for_check_code,
    heuristic_specs,
    known_heuristic_ids,
)


def test_known_heuristic_ids_match_workflow_yaml_references():
    """Every heuristic id referenced in workflow.yaml.j2 must be registered.

    The reverse direction (every registered id is referenced) is not
    required — stage 1 backfills add more references, and the registry
    is shared with the spec validator's known-id check.
    """
    from pathlib import Path

    import yaml

    template = Path("src/tripwire/templates/workflow.yaml.j2").read_text(
        encoding="utf-8"
    )
    parsed = yaml.safe_load(template)

    referenced: set[str] = set()
    for workflow in parsed.get("workflows", {}).values():
        for status in workflow.get("statuses", []):
            referenced.update(status.get("heuristics", []) or [])
        for route in workflow.get("routes", []) or []:
            controls = route.get("controls") or {}
            referenced.update(controls.get("heuristics", []) or [])

    registered = known_heuristic_ids()
    missing = referenced - registered
    assert missing == set(), (
        f"workflow.yaml.j2 references unregistered heuristics: {sorted(missing)}"
    )


def test_heuristic_specs_have_required_fields():
    for spec in heuristic_specs():
        assert spec.id.startswith("v_") or "-" in spec.id, spec.id
        assert spec.label
        assert spec.description
        assert spec.entity in {"issue", "session", "node", "project"}
        assert spec.check_code_prefix


def test_heuristic_for_check_code_exact_prefix():
    spec = heuristic_for_check_code("stale_concept/referenced")
    assert spec is not None
    assert spec.id == "v_stale_concept"


def test_heuristic_for_check_code_with_no_slash():
    spec = heuristic_for_check_code("stale_concept")
    assert spec is not None
    assert spec.id == "v_stale_concept"


def test_heuristic_for_check_code_unknown_returns_none():
    assert heuristic_for_check_code("uuid/missing") is None


def test_known_heuristic_ids_includes_all_eight_v_prefixed_ids():
    ids = known_heuristic_ids()
    expected = {
        "v_stale_concept",
        "v_concept_name_prose",
        "v_semantic_coverage",
        "v_mega_issue",
        "v_node_ratio",
        "v_coverage_heuristics",
        "v_quality_consistency",
        "v_sequence_drift",
    }
    assert expected <= ids
