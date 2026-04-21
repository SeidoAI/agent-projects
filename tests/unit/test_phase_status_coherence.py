"""Layer 2 coherence: ArtifactPhase values (minus session-only) must
exist in IssueStatus.

If anyone adds a new phase that doesn't correspond to a status, either:
- add the matching status to `issue_status.yaml`, OR
- add the phase to SESSION_ONLY_PHASES (if it's a session-lifecycle-only concept).
"""

from pathlib import Path

import yaml


SESSION_ONLY_PHASES = frozenset({"planning"})


def _load_shipped_enum_values(name: str) -> set[str]:
    """Read the tripwire-shipped default enum YAML."""
    import tripwire

    root = Path(tripwire.__file__).parent
    data = yaml.safe_load(
        (root / "templates" / "enums" / f"{name}.yaml").read_text(encoding="utf-8")
    )
    return {entry["id"] for entry in data["values"]}


def test_artifact_phases_align_with_issue_status():
    phases = _load_shipped_enum_values("artifact_phase")
    statuses = _load_shipped_enum_values("issue_status")

    overlap_required = phases - SESSION_ONLY_PHASES
    missing = overlap_required - statuses
    assert not missing, (
        f"ArtifactPhase values {sorted(missing)} have no matching IssueStatus. "
        "Either add them to issue_status.yaml, rename them, or add to "
        "SESSION_ONLY_PHASES in this test."
    )
