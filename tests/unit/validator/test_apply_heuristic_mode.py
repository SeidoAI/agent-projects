"""``_apply_heuristic_mode`` — the suppression / promotion pipeline.

The four modes (surface / quiet / none / as_tripwires) decide whether a
heuristic-class CheckResult survives, gets promoted, or is silently
dropped, and whether the marker layer is updated as a side effect.
Non-heuristic findings always pass through untouched.
"""

from __future__ import annotations

from pathlib import Path

from tripwire._internal.heuristics import has_marker, write_marker
from tripwire._internal.heuristics._acks import (
    PROJECT_SINGLETON_UUID,
    MarkerKey,
    condition_hash,
)
from tripwire.core.validator import (
    CheckResult,
    ValidationContext,
    _apply_heuristic_mode,
    _entity_uuid_for_finding,
)


def _ctx(tmp_path: Path) -> ValidationContext:
    return ValidationContext(project_dir=tmp_path)


def _heuristic_finding(
    code: str = "stale_concept/referenced",
    message: str = "node X is stale",
    file: str = "nodes/x.yaml",
) -> CheckResult:
    return CheckResult(code=code, severity="warning", message=message, file=file)


def _non_heuristic_finding() -> CheckResult:
    return CheckResult(
        code="uuid/missing", severity="error", message="missing uuid"
    )


# ============================================================================
# surface mode — default; emit + write markers as side effect.
# ============================================================================


def test_surface_passes_heuristic_findings_through(tmp_path: Path):
    finding = _heuristic_finding()
    out = _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="surface"
    )
    assert out == [finding]


def test_surface_writes_marker_for_heuristic_finding(tmp_path: Path):
    finding = _heuristic_finding()
    _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="surface"
    )
    chash = condition_hash(
        finding.code, finding.message, finding.file or "", finding.field or ""
    )
    # Heuristic for stale_concept is entity=node — no entity match in the
    # empty context, so falls back to the path-hash uuid.
    expected_uuid = f"path:{condition_hash('nodes/x.yaml')}"
    assert has_marker(
        tmp_path, MarkerKey("v_stale_concept", expected_uuid, chash)
    )


def test_surface_does_not_write_marker_for_non_heuristic(tmp_path: Path):
    finding = _non_heuristic_finding()
    _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="surface"
    )
    ack_root = tmp_path / ".tripwire" / "heuristic-acks"
    assert not ack_root.exists() or not any(ack_root.iterdir())


# ============================================================================
# quiet mode — suppress findings whose marker exists.
# ============================================================================


def test_quiet_suppresses_finding_with_existing_marker(tmp_path: Path):
    finding = _heuristic_finding()
    chash = condition_hash(
        finding.code, finding.message, finding.file or "", finding.field or ""
    )
    expected_uuid = f"path:{condition_hash('nodes/x.yaml')}"
    write_marker(tmp_path, MarkerKey("v_stale_concept", expected_uuid, chash))

    out = _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="quiet"
    )
    assert out == []


def test_quiet_emits_finding_without_marker(tmp_path: Path):
    finding = _heuristic_finding()
    out = _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="quiet"
    )
    assert out == [finding]


def test_quiet_re_fires_when_message_changes(tmp_path: Path):
    """Different message → different condition_hash → marker mismatch."""
    old = _heuristic_finding(message="evidence v1")
    new = _heuristic_finding(message="evidence v2")

    # Fire the old one so its marker exists.
    _apply_heuristic_mode(
        [old], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="surface"
    )

    out = _apply_heuristic_mode(
        [new], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="quiet"
    )
    assert out == [new], "new condition_hash should re-fire under --quiet-heuristics"


# ============================================================================
# none mode — skip every heuristic finding, no marker writes.
# ============================================================================


def test_none_mode_drops_heuristic_findings(tmp_path: Path):
    out = _apply_heuristic_mode(
        [_heuristic_finding()],
        project_dir=tmp_path,
        ctx=_ctx(tmp_path),
        mode="none",
    )
    assert out == []


def test_none_mode_does_not_write_markers(tmp_path: Path):
    _apply_heuristic_mode(
        [_heuristic_finding()],
        project_dir=tmp_path,
        ctx=_ctx(tmp_path),
        mode="none",
    )
    ack_root = tmp_path / ".tripwire" / "heuristic-acks"
    assert not ack_root.exists() or not any(ack_root.iterdir())


def test_none_mode_keeps_non_heuristic_findings(tmp_path: Path):
    err = _non_heuristic_finding()
    out = _apply_heuristic_mode(
        [err], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="none"
    )
    assert out == [err]


# ============================================================================
# as_tripwires mode — promote to error; ignore markers.
# ============================================================================


def test_as_tripwires_promotes_warning_to_error(tmp_path: Path):
    out = _apply_heuristic_mode(
        [_heuristic_finding()],
        project_dir=tmp_path,
        ctx=_ctx(tmp_path),
        mode="as_tripwires",
    )
    assert len(out) == 1
    assert out[0].severity == "error"


def test_as_tripwires_ignores_existing_marker(tmp_path: Path):
    finding = _heuristic_finding()
    chash = condition_hash(
        finding.code, finding.message, finding.file or "", finding.field or ""
    )
    expected_uuid = f"path:{condition_hash('nodes/x.yaml')}"
    write_marker(tmp_path, MarkerKey("v_stale_concept", expected_uuid, chash))

    out = _apply_heuristic_mode(
        [finding],
        project_dir=tmp_path,
        ctx=_ctx(tmp_path),
        mode="as_tripwires",
    )
    assert len(out) == 1
    assert out[0].severity == "error"


# ============================================================================
# Entity uuid resolution.
# ============================================================================


def test_project_singleton_uuid_for_project_scoped_heuristic(tmp_path: Path):
    finding = _heuristic_finding(
        code="sequence_drift/out_of_order",
        message="sequence drifted",
        file="issues/X-1/issue.yaml",
    )
    _apply_heuristic_mode(
        [finding], project_dir=tmp_path, ctx=_ctx(tmp_path), mode="surface"
    )
    chash = condition_hash(
        finding.code, finding.message, finding.file or "", ""
    )
    # v_sequence_drift's entity is "project" → marker keyed under singleton.
    assert has_marker(
        tmp_path, MarkerKey("v_sequence_drift", PROJECT_SINGLETON_UUID, chash)
    )


def test_unknown_mode_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown heuristic_mode"):
        _apply_heuristic_mode(
            [], project_dir=Path("/tmp"), ctx=ValidationContext(project_dir=Path("/tmp")),
            mode="bogus",
        )


def test_entity_uuid_resolves_from_loaded_entity(tmp_path: Path):
    from tripwire.core.validator._types import LoadedEntity

    ctx = _ctx(tmp_path)
    ctx.nodes.append(
        LoadedEntity(
            rel_path="nodes/x.yaml",
            raw_frontmatter={"uuid": "node-uuid-1"},
            body="",
            model=None,
        )
    )
    finding = _heuristic_finding()
    uuid = _entity_uuid_for_finding(finding, ctx, "node")
    assert uuid == "node-uuid-1"
