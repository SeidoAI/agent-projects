"""Themed groupings of validator check functions.

Each constant is a list of check functions sharing a domain — identity
invariants, enum-value validity, reference integrity, etc. The aggregator
:data:`ALL_CHECKS` rebuilds the canonical run order by concatenating
the themed lists in the same order they appeared pre-split.

The function bodies still live in :mod:`tripwire.core.validator` (the
god-file decomposition does the relocation in a later cycle); this
module's job is to make the registry discoverable.

Why themed lists, not one-file-per-check: ~24 checks would mean ~24
files. Each is already a well-named function; per-file isolation costs
more discoverability than it saves. Themed groupings strike a balance
that future work can refine.

The four ``LINT_CHECKS`` (under ``validator/lint/``) are appended to
``ALL_CHECKS`` separately because they're stateful rules that already
own their own files — see ``lint/__init__.py``.
"""

from __future__ import annotations

from tripwire.core.validator import (
    check_artifact_presence,
    check_bidirectional_related,
    check_comment_provenance,
    check_coverage_heuristics,
    check_enum_values,
    check_freshness,
    check_handoff_artifact,
    check_id_collisions,
    check_id_format,
    check_issue_artifact_presence,
    check_issue_body_structure,
    check_manifest_phase_ownership_consistent,
    check_manifest_schema,
    check_phase_requirements,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
    check_project_standards,
    check_quality_consistency,
    check_reference_integrity,
    check_sequence_drift,
    check_session_issue_coherence,
    check_status_transitions,
    check_timestamps,
    check_uuid_present,
)

# Identity: every entity has a uuid, the right id format, no collisions,
# the next-id counter is consistent, timestamps are parseable.
IDENTITY_CHECKS = [
    check_uuid_present,
    check_id_format,
    check_id_collisions,
    check_sequence_drift,
    check_timestamps,
]

# Enums: every enum-typed field carries a value present in the active enum.
ENUM_CHECKS = [check_enum_values]

# References: every link between entities resolves; bi-directional links stay symmetric.
REFERENCE_CHECKS = [
    check_reference_integrity,
    check_bidirectional_related,
]

# Structure: required Markdown sections in issue bodies, status transitions,
# handoff.yaml schema.
STRUCTURE_CHECKS = [
    check_issue_body_structure,
    check_status_transitions,
    check_handoff_artifact,
]

# Artifacts: manifest schema valid, completed sessions ship required artifacts.
ARTIFACTS_CHECKS = [
    check_manifest_schema,
    check_manifest_phase_ownership_consistent,
    check_artifact_presence,
    check_issue_artifact_presence,
]

# Coherence: cross-entity invariants — freshness of cached content, comment
# provenance, session-vs-issue lifecycle alignment, PM response covers
# self-review items, follow-ups close out properly.
COHERENCE_CHECKS = [
    check_freshness,
    check_comment_provenance,
    check_session_issue_coherence,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
]

# Quality: project-standards, coverage heuristics, phase requirements,
# anti-fatigue degradation detection.
QUALITY_CHECKS = [
    check_project_standards,
    check_coverage_heuristics,
    check_phase_requirements,
    check_quality_consistency,
]

# Canonical run order: concatenate themes in the same order they
# appeared in the pre-split ALL_CHECKS, so finding output ordering
# stays byte-stable.
ALL_CHECKS = [
    # Identity (uuid_present, id_format) ran before enums historically.
    check_uuid_present,
    check_id_format,
    # Enums.
    *ENUM_CHECKS,
    # References + structure.
    *REFERENCE_CHECKS,
    check_issue_body_structure,
    check_status_transitions,
    # Coherence (freshness ran before manifests historically).
    check_freshness,
    # Artifacts.
    check_manifest_schema,
    check_manifest_phase_ownership_consistent,
    check_artifact_presence,
    # Identity (id_collisions, sequence_drift, timestamps) ran after artifacts.
    check_id_collisions,
    check_sequence_drift,
    check_timestamps,
    check_comment_provenance,
    # Quality.
    check_project_standards,
    check_coverage_heuristics,
    check_phase_requirements,
    check_handoff_artifact,
    check_quality_consistency,
    check_session_issue_coherence,
    check_issue_artifact_presence,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
]


__all__ = [
    "ALL_CHECKS",
    "ARTIFACTS_CHECKS",
    "COHERENCE_CHECKS",
    "ENUM_CHECKS",
    "IDENTITY_CHECKS",
    "QUALITY_CHECKS",
    "REFERENCE_CHECKS",
    "STRUCTURE_CHECKS",
]
