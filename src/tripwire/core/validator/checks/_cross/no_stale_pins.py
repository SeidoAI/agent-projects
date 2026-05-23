"""KUI-127 / A2: pinned references whose target had a contract change."""

from __future__ import annotations

from tripwire.core.graph.refs import extract_references_with_pins
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_no_stale_pins(ctx: ValidationContext) -> list[CheckResult]:
    """KUI-127 / A2: pinned references whose target had a contract change.

    A `[[id@vN]]` pin is stale when the target entity has a PM-set
    `contract_changed_at` value strictly greater than the pin's
    version. The PM-marked path is the only path shipped in v0.9; the
    LLM-classifier path is deferred to v1.0 (TW1-6).

    Emits ``references/stale_pin`` (severity ``error``) per stale
    occurrence, with a fix-hint pointing at A5
    (``tripwire node check --update``).
    """
    results: list[CheckResult] = []

    # Build a lookup of {entity_id: contract_changed_at} across every
    # versioned entity type. Bare references resolve into either issues
    # or concept nodes today; future v1.0 work covers session/comment.
    target_marker: dict[str, int | None] = {}
    for e in ctx.issues:
        target_marker[e.model.id] = getattr(e.model, "contract_changed_at", None)
    for e in ctx.nodes:
        target_marker[e.model.id] = getattr(e.model, "contract_changed_at", None)

    def _scan(entity, body: str, *, field: str = "body") -> None:
        for ref_id, pin_version in extract_references_with_pins(body):
            if pin_version is None:
                continue  # bare ref = latest, never stale
            target_change = target_marker.get(ref_id)
            if target_change is None:
                continue  # unknown target or no contract change recorded
            if pin_version < target_change:
                results.append(
                    CheckResult(
                        code="references/stale_pin",
                        severity="error",
                        file=entity.rel_path,
                        field=field,
                        message=(
                            f"Pin [[{ref_id}@v{pin_version}]] is stale: target "
                            f"contract changed at v{target_change}."
                        ),
                        fix_hint=(
                            f"Run `tripwire node check --update {ref_id}` to "
                            "review and bump the pin to the latest version."
                        ),
                    )
                )

    for entity in ctx.issues:
        _scan(entity, entity.model.body)
    for entity in ctx.nodes:
        _scan(entity, entity.model.body)
    for entity in ctx.sessions:
        _scan(entity, entity.model.body or "")
    for entity in ctx.comments:
        _scan(entity, entity.model.body or "")

    return results
