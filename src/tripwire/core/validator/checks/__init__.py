"""Validator check functions — one ``check_*`` per file.

To add a new check:
1. Create ``<short_name>.py`` exporting ``def check_<short_name>(ctx): ...``.
   (Filename = function name minus the ``check_`` prefix.)
2. Import it below and append the function to ``ALL_CHECKS`` in the
   canonical run-order position.

Shared private helpers used by 2+ checks live in ``_helpers.py``.
Single-use helpers stay in the check file that needs them.

The four ``LINT_CHECKS`` (under ``validator/lint/``) are appended to
``ALL_CHECKS`` separately because they're stateful rules that already
own their own files — see ``lint/__init__.py``.
"""

from __future__ import annotations

from tripwire.core.validator.checks.artifact_presence import check_artifact_presence
from tripwire.core.validator.checks.bidirectional_related import (
    check_bidirectional_related,
)
from tripwire.core.validator.checks.comment_provenance import check_comment_provenance
from tripwire.core.validator.checks.coverage_heuristics import (
    check_coverage_heuristics,
)
from tripwire.core.validator.checks.done_implies_session_completed import (
    check_done_implies_session_completed,
)
from tripwire.core.validator.checks.enum_values import check_enum_values
from tripwire.core.validator.checks.freshness import check_freshness
from tripwire.core.validator.checks.handoff_artifact import check_handoff_artifact
from tripwire.core.validator.checks.id_collisions import check_id_collisions
from tripwire.core.validator.checks.id_format import check_id_format
from tripwire.core.validator.checks.instance_shape_conforms import (
    check_instance_shape_conforms,
)
from tripwire.core.validator.checks.issue_artifact_presence import (
    check_issue_artifact_presence,
)
from tripwire.core.validator.checks.issue_body_structure import (
    check_issue_body_structure,
)
from tripwire.core.validator.checks.issue_session_status_compatibility import (
    check_issue_session_status_compatibility,
)
from tripwire.core.validator.checks.manifest_phase_ownership_consistent import (
    check_manifest_phase_ownership_consistent,
)
from tripwire.core.validator.checks.manifest_schema import check_manifest_schema
from tripwire.core.validator.checks.member_issues_at_or_past_in_review import (
    check_member_issues_at_or_past_in_review,
)
from tripwire.core.validator.checks.no_stale_pins import check_no_stale_pins
from tripwire.core.validator.checks.phase_requirements import check_phase_requirements
from tripwire.core.validator.checks.pm_response_covers_self_review import (
    check_pm_response_covers_self_review,
)
from tripwire.core.validator.checks.pm_response_followups_resolve import (
    check_pm_response_followups_resolve,
)
from tripwire.core.validator.checks.pr_merged_for_session import (
    check_pr_merged_for_session,
)
from tripwire.core.validator.checks.pr_review_approved import check_pr_review_approved
from tripwire.core.validator.checks.pr_review_code_review_skill import (
    check_pr_review_code_review_skill,
)
from tripwire.core.validator.checks.pr_review_evidence import check_pr_review_evidence
from tripwire.core.validator.checks.pr_review_external_reviewer import (
    check_pr_review_external_reviewer,
)
from tripwire.core.validator.checks.pr_review_threshold_findings import (
    check_pr_review_threshold_findings,
)
from tripwire.core.validator.checks.project_repos_present import (
    check_project_repos_present,
)
from tripwire.core.validator.checks.project_standards import check_project_standards
from tripwire.core.validator.checks.quality_consistency import (
    check_quality_consistency,
)
from tripwire.core.validator.checks.reference_integrity import (
    check_reference_integrity,
)
from tripwire.core.validator.checks.sequence_drift import check_sequence_drift
from tripwire.core.validator.checks.session_has_developer_md import (
    check_session_has_developer_md,
)
from tripwire.core.validator.checks.session_has_verified_md import (
    check_session_has_verified_md,
)
from tripwire.core.validator.checks.session_issue_coherence import (
    check_session_issue_coherence,
)
from tripwire.core.validator.checks.status_transitions import check_status_transitions
from tripwire.core.validator.checks.timestamps import check_timestamps
from tripwire.core.validator.checks.uuid_present import check_uuid_present
from tripwire.core.validator.checks.workflow_well_formed import (
    check_workflow_well_formed,
)
from tripwire.core.validator.checks.workspace_link import check_workspace_link

# Canonical run order: matches the pre-split ALL_CHECKS literal so finding
# output ordering stays byte-stable. The workflow check sits where it
# always has (before workspace_link); the instance-shape check stays
# at the end so v0.9 projects without one see no perturbation.
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
    check_member_issues_at_or_past_in_review,
    check_pr_merged_for_session,
    check_pr_review_approved,
    check_session_has_developer_md,
    check_session_has_verified_md,
    check_instance_shape_conforms,
]


__all__ = ["ALL_CHECKS"]
