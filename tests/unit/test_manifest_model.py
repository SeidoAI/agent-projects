"""ArtifactManifest model and its ownership fields.

As of v0.7b, `produced_at` / `produced_by` / `owned_by` are plain strings
on the model. Enum validation now happens at manifest-load time via
`tripwire.core.manifest_loader.load_artifact_manifest`. See
`test_manifest_loader.py` for those assertions.
"""

from tripwire.models.manifest import ArtifactEntry, ArtifactManifest


class TestArtifactEntry:
    def test_parses_all_fields(self):
        entry = ArtifactEntry(
            name="plan",
            file="plan.md",
            template="plan.md.j2",
            produced_at="planning",
            produced_by="pm",
            owned_by="pm",
            required=True,
            approval_gate=False,
        )
        assert entry.produced_by == "pm"
        assert entry.owned_by == "pm"

    def test_accepts_unknown_strings_at_model_level(self):
        """Model is permissive; enum validation is loader-level."""
        entry = ArtifactEntry(
            name="plan",
            file="plan.md",
            template="plan.md.j2",
            produced_at="custom_phase",
            produced_by="wizard",
            owned_by="wizard",
            required=True,
        )
        assert entry.produced_by == "wizard"

    def test_defaults_owned_by_to_produced_by_when_absent(self):
        entry = ArtifactEntry(
            name="plan",
            file="plan.md",
            template="plan.md.j2",
            produced_at="planning",
            produced_by="pm",
            required=True,
        )
        assert entry.owned_by == "pm"


class TestArtifactManifest:
    def test_parses_full_manifest(self):
        manifest = ArtifactManifest(
            artifacts=[
                ArtifactEntry(
                    name="plan",
                    file="plan.md",
                    template="plan.md.j2",
                    produced_at="planning",
                    produced_by="pm",
                    owned_by="pm",
                    required=True,
                ),
                ArtifactEntry(
                    name="task-checklist",
                    file="task-checklist.md",
                    template="task-checklist.md.j2",
                    produced_at="in_progress",
                    produced_by="execution-agent",
                    owned_by="execution-agent",
                    required=True,
                ),
            ]
        )
        assert len(manifest.artifacts) == 2
        assert manifest.artifacts[0].owned_by == "pm"
        assert manifest.artifacts[1].produced_at == "in_progress"
