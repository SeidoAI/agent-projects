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

## How to read a failure

The tests here are **audits**, not specs you tune to match current
behaviour. When a fitness function fails, the correct response is:

1. **Look at the code, not the test.** The failure is a finding,
   like a tripwire firing for an agent. Read what the code is
   actually doing.
2. **Decide which is wrong.** Either:
   - The code drifted from intent → fix the code.
   - The philosophy claim was over-broad / outdated → update
     `docs/philosophy.md` first, then update the test.
3. **Never just add an `EXEMPT_FILES` allowlist.** That's the
   show-pony pattern: the test passes, the violation remains, and
   future readers think the carve-out was always intended. If the
   test surfaces something the philosophy doesn't acknowledge, the
   gap is real and worth resolving — not papering over.

The fitness functions in this directory have already caught three
real violations during their own development (v0.13.1 rounds 2-3):
read-only `git` subprocess inline in `validator/lint/`, the
`apply_fixes` mutator living inside `core/validator/`, and three
JSONL appenders hand-rolling the same POSIX-append pattern. All
three were fixed at the source — the tests didn't grow exemptions.

## Four kinds of test live here

### `acceptance/` — executable specifications

End-to-end behaviour tests. Each test maps to one philosophy claim.
The docstring names the section. The body proves it.

Claims currently covered:

- §9: "Agents extend tripwire by editing YAML. No Python knowledge
  needed." → `test_custom_workflow_lifecycle.py`
- §9: "`tripwire validate` is the single accountability surface." →
  `test_validate_is_single_accountability_surface.py`

### `architecture/` — fitness functions

Tests that scan the **source code itself** for forbidden patterns.
They don't run the system — they grep, parse, or AST-walk the tree
and assert structural invariants.

Claims currently covered:

- §9 C1-C3: No direct `instance.status = SomeEnum.…` outside the
  executor → `test_single_writer_guarantee.py`
- §9: No imperative keys (`script:`, `cmd:`, `exec:`, `if:`, …) and
  no script bodies in `command:` values; every workflow has an
  `instance:` block → `test_no_imperative_in_workflow_yaml.py`
- §9 rule 3: No new per-workflow Python class scaffolding — model
  files are frozen to the allowlisted set →
  `test_no_per_workflow_python_class.py`
- §9: `instance_io.py` is workflow-agnostic — no specific workflow
  id appears in its source →
  `test_instance_io_is_workflow_agnostic.py`
- §9: No validator filename matches a specific workflow id —
  validators are named by concern, not by workflow →
  `test_no_per_workflow_validator_filename.py`
- §9 + skill markdown: Every `tripwire <cmd>` mention in
  `templates/skills/**/*.md` resolves to a registered CLI →
  `test_skill_markdown_cli_references.py`
- §9 + docs: Same cross-reference for `docs/WORKFLOW_ACTIONS.md` →
  `test_workflow_actions_cli_references.py`
- §6: PM agent is the only inbox author; framework code does not
  write to `inbox/<id>.md` → `test_pm_only_inbox_authoring.py`
- §3 + §6: Validators don't reference the inbox authoring surface →
  `test_validators_do_not_write_inbox.py`
- §3 stricter: `validator/checks/` and `validator/lint/` subdirs
  perform NO filesystem mutation — `apply_fixes` in the top-level
  module is the only allowed mutator →
  `test_validator_checks_are_pure_read.py`
- §6: The HTTP route layer has no POST-create for inbox →
  `test_inbox_route_has_no_post_create.py`
- §5: InboxBucket Literal is exactly `{blocked, fyi}` →
  `test_inbox_two_buckets_only.py`
- §7: Audit log writes go through the atomic helper, never raw
  `write_text` → `test_audit_log_uses_atomic_helpers.py`
- §7: `src/tripwire/` imports no database / persistence-service
  client — filesystem-native → `test_filesystem_native.py`
- §9 + C1-C3: AST-based single-writer check catches the
  setattr/dict bypass shapes the regex companion misses →
  `test_single_writer_ast.py`
- Test hygiene: tests don't anchor to `Path.home()` /
  `os.environ["HOME"]` (AST scan) →
  `test_tests_write_only_to_tmp_path.py`
- §7: every `~/.tripwire/...` path in src/ has an env-var override
  for test isolation →
  `test_home_anchored_paths_have_env_overrides.py`
- Schema sanity: route ids are unique within each workflow →
  `test_workflow_route_ids_unique.py`
- §9: every registered CLI command has non-empty help text →
  `test_cli_commands_have_docstrings.py`
- Schema sanity: each workflow's `instance` block is internally
  consistent (status_field in required_fields; non-singleton has
  `{instance_id}`; executor-driven workflows have status_enum
  matching the statuses block) →
  `test_workflow_instance_shape_consistency.py`

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
