"""Themed groupings of validator check functions.

Each constant is a list of check functions sharing a domain — identity
invariants, enum-value validity, reference integrity, etc. The aggregator
:data:`ALL_CHECKS` rebuilds the canonical run order by concatenating
the themed lists in the same order they appeared pre-split.

The four ``LINT_CHECKS`` (under ``validator/lint/``) are appended to
``ALL_CHECKS`` separately because they're stateful rules that already
own their own files — see ``lint/__init__.py``.
"""

from __future__ import annotations

from tripwire.core.validator.checks.artifacts import (
    check_artifact_presence,
    check_issue_artifact_presence,
    check_manifest_phase_ownership_consistent,
    check_manifest_schema,
)
from tripwire.core.validator.checks.coherence import (
    check_comment_provenance,
    check_done_implies_session_completed,
    check_freshness,
    check_issue_session_status_compatibility,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
    check_session_issue_coherence,
)
from tripwire.core.validator.checks.enums import check_enum_values
from tripwire.core.validator.checks.identity import (
    check_id_collisions,
    check_id_format,
    check_sequence_drift,
    check_timestamps,
    check_uuid_present,
)
from tripwire.core.validator.checks.pr_review import (
    check_pr_review_code_review_skill,
    check_pr_review_evidence,
    check_pr_review_external_reviewer,
    check_pr_review_threshold_findings,
)
from tripwire.core.validator.checks.quality import (
    check_coverage_heuristics,
    check_phase_requirements,
    check_project_standards,
    check_quality_consistency,
)
from tripwire.core.validator.checks.references import (
    check_bidirectional_related,
    check_no_stale_pins,
    check_reference_integrity,
)
from tripwire.core.validator.checks.structure import (
    check_handoff_artifact,
    check_issue_body_structure,
    check_project_repos_present,
    check_status_transitions,
)
from tripwire.core.validator.checks.workflow import check_workflow_well_formed
from tripwire.core.validator.checks.workspace_link import check_workspace_link

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
    check_no_stale_pins,
]

# Structure: required Markdown sections in issue bodies, status transitions,
# handoff.yaml schema, project.yaml.repos presence.
STRUCTURE_CHECKS = [
    check_issue_body_structure,
    check_status_transitions,
    check_handoff_artifact,
    check_project_repos_present,
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
    check_issue_session_status_compatibility,
    check_done_implies_session_completed,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
]

# PR-review (v0.12 — handoff #3): pr-review.yaml content gates that
# block transitions to verified/completed without substantive review.
# Missing-file enforcement is handled by check_artifact_presence via
# the manifest entry's `produced_at: in_review`.
PR_REVIEW_CHECKS = [
    check_pr_review_evidence,
    check_pr_review_threshold_findings,
    check_pr_review_external_reviewer,
    check_pr_review_code_review_skill,
]

# Quality: project-standards, coverage heuristics, phase requirements,
# anti-fatigue degradation detection.
QUALITY_CHECKS = [
    check_project_standards,
    check_coverage_heuristics,
    check_phase_requirements,
    check_quality_consistency,
]

# Workflow: well-formedness of `<project>/workflow.yaml` (KUI-119).
WORKFLOW_CHECKS = [check_workflow_well_formed]

# Workspace: bidirectional project<->workspace link consistency.
WORKSPACE_CHECKS = [check_workspace_link]

# Canonical run order: matches the pre-split ALL_CHECKS literal so finding
# output ordering stays byte-stable. The workflow check is appended at
# the END so it doesn't perturb the byte-stable position of any
# pre-existing check (KUI-119 — workflow.yaml is opt-in for v0.9; ALL
# legacy projects without one see no findings from this check).
ALL_CHECKS = [
    check_uuid_present,
    check_id_format,
    check_enum_values,
    check_reference_integrity,
    check_bidirectional_related,
    check_no_stale_pins,
    check_issue_body_structure,
    check_status_transitions,
    check_freshness,
    check_manifest_schema,
    check_manifest_phase_ownership_consistent,
    check_artifact_presence,
    check_id_collisions,
    check_sequence_drift,
    check_timestamps,
    check_comment_provenance,
    check_project_standards,
    check_coverage_heuristics,
    check_phase_requirements,
    check_handoff_artifact,
    check_quality_consistency,
    check_session_issue_coherence,
    check_issue_session_status_compatibility,
    check_done_implies_session_completed,
    check_issue_artifact_presence,
    check_pm_response_covers_self_review,
    check_pm_response_followups_resolve,
    check_workflow_well_formed,
    check_workspace_link,
    check_project_repos_present,
    check_pr_review_evidence,
    check_pr_review_threshold_findings,
    check_pr_review_external_reviewer,
    check_pr_review_code_review_skill,
]


__all__ = [
    "ALL_CHECKS",
    "ARTIFACTS_CHECKS",
    "COHERENCE_CHECKS",
    "ENUM_CHECKS",
    "IDENTITY_CHECKS",
    "PR_REVIEW_CHECKS",
    "QUALITY_CHECKS",
    "REFERENCE_CHECKS",
    "STRUCTURE_CHECKS",
    "WORKFLOW_CHECKS",
    "WORKSPACE_CHECKS",
]
