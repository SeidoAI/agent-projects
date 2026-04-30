"""Named-check catalogue for the pm-review station.

The plan calls out 10 checks — schema, refs, status transition, fields,
markdown structure, freshness, artifact presence, no orphan additions,
comment provenance, project standards. Each maps to an existing
validator check function (see ``decisions.md`` D1). The mapping lives
here as a single source of truth so the runner, the artifact writer,
and the pattern-aggregator all read the same names.

The CHECK_PREFIX_TO_NAME table routes a finding's ``code`` (which is
``<prefix>/<detail>`` per the validator convention) to the named
check it belongs to. A finding whose prefix isn't mapped lands in the
``other`` bucket and degrades the verdict to ``request_changes`` —
silent fall-through is the wrong default.
"""

from __future__ import annotations

# Ordered: this is the canonical artifact + verdict ordering.
PM_REVIEW_CHECKS: list[tuple[str, str]] = [
    ("schema", "v_uuid_present"),
    ("refs", "v_reference_integrity"),
    ("status_transition", "v_status_transitions"),
    ("fields", "v_enum_values"),
    ("markdown_structure", "v_issue_body_structure"),
    ("freshness", "v_freshness"),
    ("artifact_presence", "v_artifact_presence"),
    ("no_orphan_additions", "v_bidirectional_related"),
    ("comment_provenance", "v_comment_provenance"),
    ("project_standards", "v_project_standards"),
]
"""(name, validator_id) — canonical pm-review check ordering.

The validator id is the ``v_<slug>`` form (``check_<slug>`` →
``v_<slug>``). Some named checks have multiple feeder finding-codes
(e.g. ``schema`` → ``schema/...`` and ``uuid/...``); see
:data:`CHECK_PREFIX_TO_NAME` for the full routing.
"""


# Map a finding's code prefix → pm-review check name. The order doesn't
# matter (each prefix maps to exactly one name); the table is canonical
# data the runner consults at partition time.
CHECK_PREFIX_TO_NAME: dict[str, str] = {
    # schema → uuid + schema-validation findings
    "uuid": "schema",
    "schema": "schema",
    "id": "schema",
    "timestamp": "schema",
    # refs → reference integrity findings (refs/, ref/)
    "refs": "refs",
    "ref": "refs",
    # status transition
    "status": "status_transition",
    # fields → enum + field-typed findings
    "enum": "fields",
    "field": "fields",
    # markdown structure (issue body)
    "structure": "markdown_structure",
    "issue": "markdown_structure",
    "body": "markdown_structure",
    # freshness
    "freshness": "freshness",
    "node": "freshness",
    # artifact presence
    "artifact": "artifact_presence",
    "artifacts": "artifact_presence",
    "manifest": "artifact_presence",
    "handoff": "artifact_presence",
    # no orphan additions (bidi refs)
    "bidi": "no_orphan_additions",
    "orphan": "no_orphan_additions",
    # comment provenance
    "comment": "comment_provenance",
    "provenance": "comment_provenance",
    # project standards
    "standards": "project_standards",
    "project": "project_standards",
    "quality": "project_standards",
    "coverage": "project_standards",
    "phase": "project_standards",
    "coherence": "project_standards",
}


def name_for_finding_code(code: str) -> str | None:
    """Return the pm-review check name for *code*, or ``None`` if unmapped.

    The code's prefix (the segment before the first ``/``) is what
    routes — ``schema/uuid_missing`` → ``schema``. ``None`` means the
    finding falls through to ``other`` and the verdict downgrades to
    ``request_changes`` so we never silently lose a finding.
    """
    if not code:
        return None
    prefix = code.split("/", 1)[0]
    return CHECK_PREFIX_TO_NAME.get(prefix)


__all__ = [
    "CHECK_PREFIX_TO_NAME",
    "PM_REVIEW_CHECKS",
    "name_for_finding_code",
]
