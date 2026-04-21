"""Tests for the manifest loader (enum validation at load time)."""

from pathlib import Path

from tripwire.core.enum_loader import load_enum
from tripwire.core.manifest_loader import load_artifact_manifest


def _write_manifest(project_dir: Path, yaml_body: str) -> Path:
    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml_body, encoding="utf-8")
    return manifest_path


def test_load_enum_falls_back_to_packaged_template(tmp_path):
    """Without a project override, tripwire's shipped template is used."""
    values = load_enum(tmp_path, "artifact_phase")
    assert "planning" in values
    assert "in_progress" in values
    assert "in_review" in values
    assert "verified" in values
    assert "done" in values


def test_load_enum_project_override_wins(tmp_path):
    """Project override supersedes packaged template."""
    (tmp_path / "enums").mkdir()
    (tmp_path / "enums" / "artifact_phase.yaml").write_text(
        "name: ArtifactPhase\nvalues:\n  - id: only_this_phase\n",
        encoding="utf-8",
    )
    values = load_enum(tmp_path, "artifact_phase")
    assert values == ["only_this_phase"]


def test_load_manifest_accepts_valid(tmp_path):
    _write_manifest(
        tmp_path,
        """
artifacts:
  - name: plan
    file: plan.md
    template: plan.md.j2
    produced_at: planning
    produced_by: pm
""",
    )
    manifest, findings = load_artifact_manifest(tmp_path)
    assert findings == []
    assert manifest is not None
    assert manifest.artifacts[0].name == "plan"


def test_load_manifest_flags_unknown_phase(tmp_path):
    _write_manifest(
        tmp_path,
        """
artifacts:
  - name: plan
    file: plan.md
    template: plan.md.j2
    produced_at: made_up_phase
    produced_by: pm
""",
    )
    _manifest, findings = load_artifact_manifest(tmp_path)
    codes = [f.code for f in findings]
    assert "manifest_schema/produced_at_valid" in codes


def test_load_manifest_flags_unknown_agent_type(tmp_path):
    _write_manifest(
        tmp_path,
        """
artifacts:
  - name: plan
    file: plan.md
    template: plan.md.j2
    produced_at: planning
    produced_by: wizard
""",
    )
    _manifest, findings = load_artifact_manifest(tmp_path)
    codes = [f.code for f in findings]
    assert "manifest_schema/produced_by_valid" in codes


def test_load_manifest_missing_file_returns_none(tmp_path):
    manifest, findings = load_artifact_manifest(tmp_path)
    assert manifest is None
    assert findings == []
