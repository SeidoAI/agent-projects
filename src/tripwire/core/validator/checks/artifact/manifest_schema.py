"""Artifact manifest schema validity."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _load_manifest


def check_manifest_schema(ctx: ValidationContext) -> list[CheckResult]:
    """`templates/artifacts/manifest.yaml` parses and matches the schema.

    Emits `manifest_schema/produced_by_valid` or `manifest_schema/owned_by_valid`
    when those enum-like fields carry an unknown agent type.
    """
    _, findings = _load_manifest(ctx)
    return findings
