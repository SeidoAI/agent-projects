"""Validator station registration (KUI-120).

Each existing validator check declares its workflow station via the
``@registers_at`` decorator. The registry exposes the
station-to-validator mapping consumed by the gate runner (KUI-159).
Behaviour during ``tripwire validate`` stays byte-stable: the same
checks run in the same order; the registry is enrichment metadata.
"""

from __future__ import annotations


def test_every_check_in_all_checks_is_registered() -> None:
    """Every function in ``ALL_CHECKS`` must declare a station via
    ``@registers_at``. The registry attribute is set as a function
    attribute by the decorator; an undecorated check would silently
    fall out of the gate runner's view."""
    from tripwire.core.validator.checks import ALL_CHECKS

    undecorated = [
        fn.__name__
        for fn in ALL_CHECKS
        if not getattr(fn, "__tripwire_workflow_station__", None)
    ]
    assert not undecorated, (
        f"checks missing @registers_at: {undecorated}. Each ALL_CHECKS "
        f"entry must declare its (workflow, station)."
    )


def test_register_at_populates_validator_registry() -> None:
    """Importing the check modules must populate the registry — accessed
    via :func:`known_validator_ids`. Empty after Step 1 ships, populated
    after Step 2 decorates the existing checks."""
    # Importing checks/__init__.py executes the decorators on every
    # check function, which flips the registry's _validator_stations
    # to a non-empty mapping.
    import tripwire.core.validator.checks  # noqa: F401
    from tripwire.core.workflow.registry import known_validator_ids

    ids = known_validator_ids()
    # Use a representative subset rather than the full set so reordering
    # one check doesn't churn the test.
    for vid in (
        "v_uuid_present",
        "v_enum_values",
        "v_reference_integrity",
        "v_artifact_presence",
    ):
        assert vid in ids, f"{vid} missing from validator registry: {sorted(ids)}"


def test_validators_for_station_returns_registered_ids() -> None:
    import tripwire.core.validator.checks  # noqa: F401
    from tripwire.core.workflow.registry import validators_for_station

    executing = validators_for_station("coding-session", "executing")
    in_review = validators_for_station("coding-session", "in_review")

    assert "v_uuid_present" in executing
    assert "v_artifact_presence" in in_review


def test_validate_byte_stable_after_registration(tmp_path) -> None:
    """`tripwire validate --strict` produces the same finding codes in
    the same order before and after the registration refactor.

    We can't compare the *exact* before/after on the same call (we are
    after the refactor), so instead we assert a hard invariant: the
    sequence of check function names in ALL_CHECKS matches a frozen
    canonical list. Touching the order is a deliberate decision, not a
    side effect of refactoring."""
    from tripwire.core.validator.checks import ALL_CHECKS

    canonical = [
        "check_uuid_present",
        "check_id_format",
        "check_enum_values",
        "check_reference_integrity",
        "check_bidirectional_related",
        # KUI-127 (v0.9 entity-graph-substrate, PR #74) added stale-pin
        # validation in the references group; canonical position is here.
        "check_no_stale_pins",
        "check_issue_body_structure",
        "check_status_transitions",
        "check_freshness",
        "check_manifest_schema",
        "check_manifest_phase_ownership_consistent",
        "check_artifact_presence",
        "check_id_collisions",
        "check_sequence_drift",
        "check_timestamps",
        "check_comment_provenance",
        "check_project_standards",
        "check_coverage_heuristics",
        "check_phase_requirements",
        "check_handoff_artifact",
        "check_quality_consistency",
        "check_session_issue_coherence",
        "check_issue_artifact_presence",
        "check_pm_response_covers_self_review",
        "check_pm_response_followups_resolve",
        "check_workflow_well_formed",
    ]
    actual = [fn.__name__ for fn in ALL_CHECKS]
    assert actual == canonical
