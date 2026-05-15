# Philosophy tests

Tests that pin down the framework's *intent*, not just its behaviour.

Each test here maps to a numbered claim in `docs/philosophy.md` (or to
a load-bearing principle in `docs/philosophy/workflow.md`). The body
of the test is the proof that the claim holds in code.

These tests exist because agent-driven development drifts. The
implementation can stay green while the philosophy quietly bends.
A working acceptance test is an executable spec. A failing fitness
function is an instant alarm that someone (human or agent) tried
to add a forbidden pattern.

## Four kinds of test live here

### `acceptance/` — executable specifications

End-to-end behaviour tests. Each test maps to one philosophy claim.
The docstring names the section. The body proves it.

Example claims that need a test:

- §9: "Agents extend tripwire by editing YAML. No Python knowledge
  needed." → `test_custom_workflow_lifecycle.py`
- §3: "Tripwires don't auto-create inbox entries." → a route layer test
- §9: "`tripwire validate` is the single accountability surface." → a
  test that hits every workflow's invariants via one `validate` call

### `architecture/` — fitness functions

Tests that scan the **source code itself** for forbidden patterns.
They don't run the system — they grep, parse, or AST-walk the tree
and assert structural invariants.

Examples:

- No direct `instance.status = …` assignment outside `transitions.py`
- No `script:` / `cmd:` / `exec:` keys in `workflow.yaml.j2`
- No `Path.write_text(...)` for files that should use atomic helpers
- Every workflow in `workflow.yaml.j2` declares an `instance:` block

These prevent agent drift at the source — an agent that adds a
forbidden pattern is caught immediately, not after a behaviour
regression slips by.

The name "fitness function" comes from *Building Evolutionary
Architectures* (Ford, Parsons, Kua). In Python they're plain pytest
tests that grep the source tree.

### `extensibility/` — schema evolution

Tests that verify the framework's *evolvability* claims. Philosophy
§9 says agents can adjust workflows via YAML. These tests prove that
adjustments don't break existing instances.

Examples:

- Adding a new status to an existing workflow keeps existing instances
  valid
- Adding a new route between existing statuses leaves earlier transitions
  legal
- Renaming a workflow's `storage_path` with the migrate CLI preserves
  instance data

### `matrix/` — behavioural invariant tables

Parametrized tests where each row asserts an invariant. The test body
is small; the value lives in the table of `(scenario, expected)` rows.

Examples:

- `test_validator_finding_matrix.py` — for each violation type, the
  validator produces a specific named finding id
- `test_transition_rejection_matrix.py` — for each illegal transition,
  the executor returns a specific rejection reason

## How to add a test

1. Pick the category that fits (see above).
2. Name the test after the **intent** it proves, not the function it
   calls. `test_custom_workflow_can_be_declared_and_used` not
   `test_execute_transition_with_unknown_workflow`.
3. Top-of-file docstring names the philosophy section. Test docstring
   quotes the specific claim.
4. Body should read like a spec, not like setup code. Push fixture
   noise into helpers.
5. When a test fails, the error message should tell a future reader
   *which philosophy claim broke*, not just `assert x == y`.

## What does NOT live here

- Unit tests for individual functions — those stay in `tests/unit/`.
- Integration tests for specific features — `tests/integration/`.
- UI tests — `tests/ui/` and `web/e2e/`.

If a test would still make sense after the philosophy doc is rewritten,
it doesn't belong here.
