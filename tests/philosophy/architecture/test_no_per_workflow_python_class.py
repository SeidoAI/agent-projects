"""Adding a workflow does not add a Python class.

Philosophy §9 rule 3:

    *"No per-workflow Python class scaffolding. Adding a workflow is
    declaring it in YAML. Side-effects only when a repetitive external
    operation needs codifying."*

This is the structural promise behind the "extend via YAML" claim. If
adding a workflow forced you to also write a Python class — a
``ReleaseTrackingInstance(BaseModel)``, a ``MaintenanceRunStore``, a
``TriageRunService`` — then "no Python knowledge needed" is false.

The codebase has four grandfathered typed entity models that predate
the v0.13.1 thin-executor refactor:

  - ``AgentSession`` (coding-session workflow)
  - ``Issue`` (issue-closure workflow)
  - ``ConceptNode`` (concept-freshness workflow)
  - ``ProjectConfig`` (phase-advancement workflow, ``phase`` field)

The other eight workflows declared in ``workflow.yaml.j2``
(``pr-lifecycle``, ``code-review``, ``pm-scoping``, ``pm-triage``,
``pm-monitor``, ``project-maintenance``, ``pm-incremental-update``,
``inbox-handling``) flow through the generic dict-based loader in
:mod:`tripwire.core.workflow.instance_io`. They have NO typed
Python class.

This fitness function pins that promise: the inventory of files
under ``src/tripwire/models/`` is fixed. Adding a new model file is
not forbidden — but it requires a deliberate update to the allowlist
here AND a §9-grounded justification (e.g. "this model represents
a non-workflow domain object, not a workflow instance"). The cost is
intentional: it's the friction §9 needs to keep the framework
extensible by YAML alone.
"""

from __future__ import annotations

from pathlib import Path

import tripwire

MODELS_ROOT = Path(tripwire.__file__).parent / "models"

# The known inventory of model files. To add to this list:
#
#   1. Decide what philosophy section justifies the model. If it's a
#      new workflow's typed wrapper, §9 says no — use the generic
#      dict loader instead.
#   2. If the model represents a non-workflow domain object (graph
#      shape, freshness derivation, prompt-check artifact, etc.),
#      add it here with a one-line comment explaining the category.
#   3. If the model wraps an existing grandfathered workflow's
#      sub-shape, justify why a separate class beats inlining.
ALLOWED_MODEL_FILES = {
    # Grandfathered workflow-instance models (predate the v0.13.1
    # thin-executor / generic-loader refactor).
    "session.py",  # coding-session workflow (AgentSession)
    "issue.py",  # issue-closure workflow (Issue)
    "node.py",  # concept-freshness workflow (ConceptNode)
    "project.py",  # phase-advancement workflow (ProjectConfig.phase)
    # Non-workflow domain models.
    "enums.py",  # IssueStatus / SessionStatus / NodeStatus enums
    "comment.py",  # per-instance comment sub-entity
    "graph.py",  # derived dependency / concept graph index
    "handoff.py",  # session-to-PM handoff artifact
    "inbox.py",  # PM-authored inbox entry schema (read-shape)
    "insights.py",  # session insights aggregate
    "issue_artifacts.py",  # per-issue developer.md / verified.md
    "manifest.py",  # project artifact manifest declaration
    "pr_review.py",  # PR-review artifact (multi-lens findings)
    "spawn.py",  # session-spawn invocation parameters
    "workspace.py",  # workspace (multi-project root) entity
}


def test_models_directory_inventory_is_frozen():
    """The set of model files is the allowlist above.

    A NEW file in ``src/tripwire/models/`` requires a deliberate
    allowlist update with a category justification. The friction is
    the test's job — it makes "I'll just add a class for this new
    workflow" impossible to do silently.
    """
    actual = {
        p.name
        for p in MODELS_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
    }

    added = actual - ALLOWED_MODEL_FILES
    removed = ALLOWED_MODEL_FILES - actual

    msg_parts = []
    if added:
        msg_parts.append(
            f"NEW model files appeared without philosophy review:\n"
            f"  {sorted(added)}\n"
            f"\n"
            f"Before allowlisting, answer:\n"
            f"  - Is this a workflow's typed instance wrapper? If yes, §9 says\n"
            f"    no — use the generic dict loader (instance_io) instead.\n"
            f"  - Is this a non-workflow domain object? Add to ALLOWED_MODEL_FILES\n"
            f"    with a one-line category comment.\n"
            f"  - Is this wrapping a grandfathered model's sub-shape? Justify\n"
            f"    why a new class beats inlining."
        )
    if removed:
        msg_parts.append(
            f"Model files REMOVED but still in allowlist:\n"
            f"  {sorted(removed)}\n"
            f"\n"
            f"Update ALLOWED_MODEL_FILES — and if you removed a grandfathered\n"
            f"entity model, update `docs/philosophy.md` §9 too."
        )

    assert not msg_parts, "Philosophy §9 inventory check failed.\n\n" + "\n\n".join(
        msg_parts
    )
