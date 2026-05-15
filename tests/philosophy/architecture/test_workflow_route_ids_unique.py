"""Every workflow's route ids are unique within that workflow.

Schema sanity check. ``workflow.yaml.j2`` declares routes per workflow.
The route ``id`` is used for:

  - Audit log entries (``route_id`` field).
  - Tripwire / prompt-check correlation.
  - Cross-references between docs and code.

Two routes within the same workflow sharing an ``id`` would silently
break the audit story: an audit-log query for a specific route would
return events from both. The schema doesn't currently enforce
uniqueness, so a YAML typo could land — this fitness function catches
it at test time.

(Uniqueness ACROSS workflows is not required: ``drafting-to-published``
in ``release-tracking`` and ``drafting-to-published`` in some future
workflow would be fine — every audit record carries both workflow and
route, so the pair is unique.)
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire

WORKFLOW_TEMPLATE = Path(tripwire.__file__).parent / "templates" / "workflow.yaml.j2"


def test_route_ids_unique_within_each_workflow():
    """Per-workflow uniqueness of ``route.id``.

    A duplicate id is a schema bug — usually a copy-paste typo when
    a new route was added. Catch at test time, fix at the source.
    """
    spec = yaml.safe_load(WORKFLOW_TEMPLATE.read_text(encoding="utf-8"))
    workflows = spec.get("workflows", {})

    violations: list[str] = []
    for wf_id, body in workflows.items():
        routes = body.get("routes") or []
        seen: dict[str, int] = {}
        duplicates: list[tuple[str, int]] = []
        for idx, route in enumerate(routes):
            if not isinstance(route, dict):
                continue
            rid = route.get("id")
            if rid is None:
                continue
            if rid in seen:
                duplicates.append((rid, idx))
            else:
                seen[rid] = idx
        for rid, idx in duplicates:
            violations.append(
                f"  {wf_id}.routes[{idx}]: duplicate id {rid!r} "
                f"(first at index {seen[rid]})"
            )

    assert not violations, (
        "Schema sanity violation — duplicate route id within a workflow.\n"
        "Route ids must be unique per-workflow so audit-log queries and\n"
        "cross-references resolve unambiguously.\n"
        "\n"
        "Offending sites:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: rename one of the colliding routes to reflect what makes\n"
        "it distinct from the other (often `<from>-to-<to>-<reason>`)."
    )
