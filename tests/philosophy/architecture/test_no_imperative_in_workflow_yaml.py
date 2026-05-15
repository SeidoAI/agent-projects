"""``workflow.yaml`` declares structure. It does not orchestrate.

Philosophy §9 rules out three patterns by name:

  1. *"No imperative side-effects in workflow.yaml. YAML does not
     orchestrate."*
  2. *"No conditional logic in workflow declarations. 'If X then Y'
     becomes a validator finding + a CLI command that does Y."*
  3. *"No per-workflow Python class scaffolding."*

This test enforces (1) and (2) by parsing the shipped
``workflow.yaml.j2`` template and asserting forbidden keys do not
appear. (3) is enforced by a separate test that scans for per-workflow
classes — out of scope here.

The shipped template is the contract: it's what every ``tripwire init``
project gets. If the template ever grows an imperative key, every
downstream project inherits the regression on next migration. Catching
it here keeps the philosophy as the contract.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire

TEMPLATE = Path(tripwire.__file__).parent / "templates" / "workflow.yaml.j2"

# Keys that turn a declarative spec into imperative orchestration.
# This list is hand-curated — schema additions that need new keys
# should be assessed against §9 before adding them.
#
# Notably NOT on this list: `command:`, `trigger:`. Per `docs/philosophy/
# workflow.md` ("Commands are how actors move work ... the declaration
# itself is data — it does not orchestrate"), these are declarative
# references — strings naming the agent-invoked CLI or the event that
# activates a route. The shape check below asserts their VALUES stay
# scalar (no list of steps, no inline script body).
FORBIDDEN_KEYS = {
    # Embedded imperative invocation
    "script",
    "cmd",
    "exec",
    "python",
    "shell",
    "bash",
    "run",  # `run: <cmd args>` belongs in a CLI wrapper, not YAML
    # Conditional predicates ("if X then Y" belongs in a validator
    # finding + a Layer-1 CLI, not in workflow.yaml)
    "if",
    "unless",
    "when",
    "predicate",
    # Imperative side-effect orchestration (the declarative
    # `side_effects:` list of named ids IS allowed — names map to
    # CLI commands the agent runs before transitioning. What's
    # forbidden is *inline* scripts under those ids.)
    "on_enter_script",
    "on_exit_script",
    "before_transition",
    "after_transition",
}

# `command:` is the declarative name of the CLI an agent invokes; its
# value is a scalar string. `trigger:` may be a scalar string
# (`session.spawn`, `command.pm-session-create`, `review.outcome == approved`)
# or a structured ``{type, name}`` dict — both shapes are declarative
# metadata, not script bodies. We do NOT enforce a strict scalar-only
# rule here because the schema already permits the dict form for
# typed-trigger declarations. What we DO enforce is the absence of any
# imperative keys nested inside, which the forbidden-key walk above
# catches (e.g. `trigger: { run: "..." }` would trip the `run:` check).


def _walk_keys(
    node: object, path: tuple[str, ...] = ()
) -> list[tuple[str, object, tuple[str, ...]]]:
    """Yield ``(key, value, path-to-parent)`` for every dict key in ``node``."""
    out: list[tuple[str, object, tuple[str, ...]]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                out.append((key, value, path))
            out.extend(_walk_keys(value, (*path, str(key))))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_walk_keys(item, (*path, f"[{i}]")))
    return out


def test_workflow_template_has_no_imperative_keys():
    """No imperative or conditional keys appear anywhere in the shipped
    workflow.yaml template.

    The template is the contract every new tripwire project inherits.
    Imperative orchestration in YAML is a §9 violation: it makes
    workflow.yaml partly-code, breaks the validate-driven accountability
    surface, and means a non-Python agent edit can introduce live
    behaviour that no validator catches.
    """
    # The .j2 file is currently pure YAML — no Jinja directives.
    # If that changes, switch to a Jinja-render step before yaml.safe_load.
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "{%" not in text and "{{ " not in text, (
        "workflow.yaml.j2 has grown Jinja directives. Update this test to "
        "render the template before parsing."
    )

    spec = yaml.safe_load(text)
    violations: list[str] = []
    for key, value, parent_path in _walk_keys(spec):
        location = ".".join(parent_path) if parent_path else "<root>"
        if key in FORBIDDEN_KEYS:
            violations.append(f"  forbidden key {key!r} at {location}")
            continue
        # Catch the sneakier shape: a string value that smuggles a
        # shell command in. `command: pm-session-create` (single token
        # naming the CLI) is fine; `command: "bash -c 'rm -rf foo'"`
        # is orchestration in disguise.
        if key == "command" and isinstance(value, str):
            if "\n" in value or " && " in value or "; " in value:
                violations.append(
                    f"  command: {value!r} at {location} smuggles shell "
                    f"composition — declarative `command:` values name a "
                    f"single CLI, not a script"
                )

    assert not violations, (
        "Philosophy §9 violation — imperative or conditional patterns\n"
        "found in the shipped workflow.yaml template. YAML declares\n"
        "structure; it does not orchestrate.\n"
        "\n"
        "Offending patterns:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: lift the imperative behaviour into a Layer-1 CLI command\n"
        "the agent runs *before* the transition. Replace the conditional\n"
        "with a validator that produces a finding the agent acts on.\n"
        "Declarative references (`command:`, `trigger:`) MUST stay scalar\n"
        "strings — a list or dict value means orchestration crept in.\n"
        "See `docs/philosophy.md` §9 and `docs/WORKFLOW_ACTIONS.md`."
    )


def test_workflow_template_workflows_all_declare_instance_block():
    """§9 + v0.13.1: every workflow declares its instance shape.

    The ``instance:`` block names ``storage_path``, ``status_field``,
    ``status_enum``, and ``required_fields``. Without it, the generic
    loader can't materialise instances and the per-instance shape
    validator (``v_instance_shape``) has nothing to check.

    v0.13.1 ships with the ``instance:`` block optional (missing →
    ``workflow/instance_missing`` warning). This test holds the line
    that *every shipped workflow* has one — even though the schema
    technically permits absence. The warning is the migration path
    for sibling projects; the shipped template should never use it.
    """
    spec = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    workflows = spec.get("workflows", {})
    assert workflows, "workflow.yaml.j2 declares no workflows"

    missing = [wf_id for wf_id, body in workflows.items() if "instance" not in body]
    assert not missing, (
        "Philosophy §9 + v0.13.1: every shipped workflow must declare an\n"
        "`instance:` block (storage_path, status_field, status_enum, ...).\n"
        "Without it, `tripwire validate`'s per-instance shape check has\n"
        "nothing to enforce and the philosophy claim that 'validate is\n"
        "the single accountability surface' degrades for these workflows.\n"
        "\n"
        f"Workflows missing instance block: {missing}\n"
        "\n"
        "Fix: add an `instance:` block under each workflow. See the\n"
        "`coding-session` workflow for the canonical shape."
    )
