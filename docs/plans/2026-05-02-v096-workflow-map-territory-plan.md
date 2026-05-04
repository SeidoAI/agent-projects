# v0.9.6 Workflow Map Territory Implementation Plan

**Date:** 2026-05-02

**Spec:** `docs/specs/2026-05-02-v096-workflow-map-territory.md`

**Philosophy:** `docs/philosophy/workflow.md`

This is the execution plan for the Workflow page revamp. It assumes the
same branch and PR stay open while the implementation proceeds.

## Objective

Replace the current Workflow page with a workflow-territory map driven by
`workflow.yaml`.

The final result should:

- use `status` vocabulary instead of `station`
- treat `workflow.yaml` as canonical
- render statuses as unequal-width regions
- render attempted status changes as transition borders
- group validators and prompt checks into gate clusters
- render JIT prompts as interventions
- render artifacts from workflow declarations
- show static process complexity, not live runtime health
- keep drift as a definition-integrity overlay
- have unit and E2E tests that catch duplicate keys, console warnings,
  blank renders, stale vocabulary, and drawer regressions

## Working Rules

- Use hard migration. Do not keep `stations:` aliases or legacy API
  fields unless an active caller outside this repo is proven.
- Commit at the end of each phase.
- Keep each phase independently reviewable.
- Do not start the frontend territory renderer until the backend
  response shape and fixtures are stable.
- Prefer deleting the old dual canvas/panel model over layering the new
  map on top of it.
- Treat role-based JIT prompt redaction as a separate product concern.
  The visual map hides detail for comprehension, not secrecy.
- Run targeted tests after each phase and full validation before final
  push/CI monitoring.

## Phase 0 - Inventory And Baseline

Goal: get a precise list of files and tests that must move from
`station` to `status`.

Run:

```sh
rg -n "\bstation\b|\bstations\b|Station|Stations|__tripwire_workflow_station__|fires_on_station|wired_to_station|wired_from_station|from_station|to_station|unknown_next_station|duplicate_station_id" src tests web docs
```

Expected hotspots:

- `src/tripwire/core/workflow/schema.py`
- `src/tripwire/core/workflow/loader.py`
- `src/tripwire/core/workflow/registry.py`
- `src/tripwire/core/workflow/transitions.py`
- `src/tripwire/core/events/schema.py`
- `src/tripwire/core/events/log.py`
- `src/tripwire/core/validator/checks/workflow.py`
- `src/tripwire/templates/workflow.yaml.j2`
- `src/tripwire/ui/services/workflow_service.py`
- `web/src/lib/api/endpoints/workflow.ts`
- `web/src/features/workflow/*`
- workflow Python tests
- workflow frontend tests
- integration/UI fixtures

Deliverable:

- no code changes unless a baseline test is clearly stale
- short note in the commit message or PR summary with the actual touched
  surface list

Verification:

```sh
uv run pytest -q tests/unit/core/test_workflow_schema.py tests/ui/services/test_workflow_service.py
cd web && npm test -- src/__tests__/features/workflow/test_WorkflowMap.test.tsx
```

Commit: no commit unless files changed.

## Phase 1 - Schema And Template Hard Migration

Goal: make `workflow.yaml` use `statuses:` as the canonical schema.

Changes:

- Rename dataclasses and fields:
  - `Station` -> `WorkflowStatus` or `Status`
  - `Workflow.stations` -> `Workflow.statuses`
  - `stations_by_id` -> `statuses_by_id`
- Loader reads `statuses:` only.
- Loader reports stale `stations:` as a validation/load finding, not as
  accepted input.
- Finding codes change:
  - `workflow/duplicate_station_id` -> `workflow/duplicate_status_id`
  - `workflow/unknown_next_station` -> `workflow/unknown_next_status`
  - `workflow/terminal_with_next` message should say status
  - `workflow/no_terminal_station` -> `workflow/no_terminal_status`
  - `workflow/missing_next_or_terminal` message should say status
- Update `src/tripwire/templates/workflow.yaml.j2` to emit
  `statuses:`.
- Add artifact declarations to the template under relevant statuses.

Tests:

- schema parses `statuses:`
- schema rejects or reports stale `stations:`
- single, conditional, terminal transitions still parse
- duplicate status, unknown next status, no terminal status all produce
  renamed finding codes
- fresh init renders `workflow.yaml` with `statuses:` and artifacts

Targeted verification:

```sh
uv run pytest -q tests/unit/core/test_workflow_schema.py tests/integration/test_init.py
```

Commit: `Migrate workflow schema to statuses`

## Phase 2 - Registry, Runtime, Events, And Drift Vocabulary

Goal: move internal workflow runtime language from station to status.

Changes:

- Rename workflow registration metadata:
  - `__tripwire_workflow_station__` -> `__tripwire_workflow_status__`
  - `validators_for_station` -> `validators_for_status`
  - `jit_prompts_for_station` -> `jit_prompts_for_status`
  - `prompt_checks_for_station` -> `prompt_checks_for_status`
- Rename decorator/help text as needed.
- Update validator registration call sites.
- Update JIT prompt `at = ("workflow", "status")` comments and tests.
- Update prompt-check frontmatter collection semantics.
- Update transition runtime:
  - `to_station` -> `to_status`
  - `from_station` -> `from_status`
  - event details use `status`, `from_status`, `to_status`
- Update drift report code and tests to status vocabulary.

Important semantic rule:

- Controls declared on a status gate attempts to enter that status.
  They are not ambient checks for work already inside the status.

Tests:

- validator registration resolves by status
- JIT prompt registration resolves by status
- prompt checks resolve by status
- transition CLI gates by attempted target status
- workflow events use status fields
- drift findings use status vocabulary

Targeted verification:

```sh
uv run pytest -q \
  tests/unit/core/test_workflow_validator_registration.py \
  tests/unit/core/test_workflow_jit_prompt_registration.py \
  tests/unit/core/test_workflow_prompt_check_mapping.py \
  tests/unit/cli/test_workflow_transition_cli.py \
  tests/unit/core/test_workflow_events_log.py \
  tests/unit/test_drift_report.py \
  tests/integration/test_workflow_e2e.py
```

Commit: `Rename workflow runtime to statuses`

## Phase 3 - Workflow API Shape

Goal: expose `workflow.yaml` directly as a workflow-first API payload.

Changes:

- Replace dual legacy response:
  - remove `lifecycle.stations`
  - remove top-level hardcoded `validators`, `jit_prompts`,
    `connectors`, `artifacts` canvas model
- Add:
  - `workflows[*].statuses`
  - `registry.validators`
  - `registry.jit_prompts`
  - `registry.prompt_checks`
  - `drift.findings`
- Keep registry metadata shallow:
  - id
  - label
  - description
  - blocking/advisory where known
- Derive artifact refs from `workflow.yaml` status declarations.
- Keep topology entirely under `workflows[*].statuses`.

Tests:

- `/api/projects/{pid}/workflow` returns `statuses`
- response does not contain legacy `lifecycle.stations`
- response does not contain `fires_on_station`
- registry metadata joins known validators/JIT prompts/prompt checks
- artifacts come from `workflow.yaml`
- PM/non-PM role behavior is preserved only where existing product
  behavior still needs it

Targeted verification:

```sh
uv run pytest -q tests/ui/routes/test_workflow_route.py tests/ui/services/test_workflow_service.py tests/integration/ui/test_pm_mode_redaction.py
```

Commit: `Expose workflow API as status territory`

## Phase 4 - Frontend Types And Data Derivation

Goal: make the frontend consume the new API shape and derive territory
layout data from `workflow.yaml` statuses.

Changes:

- Update `web/src/lib/api/endpoints/workflow.ts`:
  - `WorkflowYamlStation` -> `WorkflowStatus`
  - `stations` -> `statuses`
  - new `registry` and `drift` types
  - remove legacy lifecycle/canvas types
- Replace `computeWorkflowLayout` with a territory data builder:
  - input: selected `WorkflowDefinition`
  - output: status regions, transition routes, gate clusters, JIT
    markers, artifact refs, drift indicators
- Compute static complexity per status:
  - validators
  - prompt checks
  - JIT prompts
  - artifacts
  - branches
  - incoming/outgoing transitions
- Compute status width from complexity:
  - minimum width for simple statuses
  - larger width for complex statuses
  - bounded maximum so one status cannot consume the whole canvas
- Compute branch classification:
  - forward
  - return
  - terminal
  - side

Tests:

- status regions are produced from `workflows[*].statuses`
- no legacy layout input is required
- complexity changes status width within min/max bounds
- branches are classified predictably
- artifacts come from status declarations
- duplicate IDs across different statuses do not produce duplicate React
  keys

Targeted verification:

```sh
cd web && npm test -- src/__tests__/api/workflow.test.tsx src/__tests__/features/workflow/test_useWorkflowLayout.test.ts
```

Commit: `Derive workflow territory data in frontend`

## Phase 5 - Territory Renderer

Goal: replace the old workflow canvas and YAML panel with one coherent
map.

Component target:

```text
WorkflowMap
  WorkflowToolbar
  WorkflowTerritory
    StatusRegion
      ControlShelf
      StatusBody
      EvidenceShelf
    TransitionRoute
      GateCluster
      JitPromptMarker
    BoundaryPort
  WorkflowDrawer
```

Layout rules:

- Desktop:
  - statuses flow west to east
  - each status is a region, not a node
  - control shelf sits above the status body
  - evidence shelf sits below the status body
  - transitions connect region borders
  - return routes bend west
  - exceptional/side routes are visually secondary
- Mobile:
  - statuses stack vertically
  - control shelf remains above body
  - evidence shelf remains below body
  - transitions become vertical connectors
- Text must not scale with viewport width.
- Detail is hidden through progressive disclosure, not tiny typography.

Visual grammar:

- Status region:
  - quiet filled territory
  - clear label
  - optional complexity badge
  - distinct control/evidence shelves
- Gate cluster:
  - border/checkpoint visual
  - count badge
  - blocking/advisory indicator
  - not a large peer card
- JIT prompt:
  - intervention marker
  - visibly different from gate
  - anchored to status or transition moment
- Artifact:
  - proof/document chip in evidence shelf
  - not a workflow step
- Drift:
  - small definition-integrity marker
  - opens drawer
  - does not recolor page as runtime failure

Interactions:

- click status: opens status overview drawer
- click gate cluster: opens gate drawer
- click JIT marker: opens JIT prompt drawer
- click artifact: opens artifact drawer
- click drift marker: opens drift drawer
- hover/focus: highlights attached transition/status only
- keyboard:
  - every clickable map object is reachable by tab
  - Escape closes drawer
  - Enter/Space activates focused object

Tests:

- one renderer, no `WorkflowsPanel`
- all key objects render with accessible names
- drawers open for status, gate, JIT prompt, artifact, and drift
- no React key warnings
- no console warnings/errors
- text does not overflow in known fixtures

Targeted verification:

```sh
cd web && npm test -- \
  src/__tests__/features/workflow/test_WorkflowMap.test.tsx \
  src/__tests__/features/workflow/test_WorkflowDrawer.test.tsx \
  src/__tests__/features/workflow/test_cards.test.tsx
```

Commit: `Render workflow territory map`

## Phase 6 - E2E Coverage

Goal: catch the problems that unit tests previously missed.

Add or update Playwright tests under `web/e2e`.

Coverage:

- route loads `/p/:projectId/workflow`
- page is nonblank
- browser console has no warnings/errors
- no duplicate-key React warning appears
- desktop screenshot smoke
- mobile screenshot smoke
- gate drawer opens
- JIT prompt drawer opens
- artifact drawer opens
- drift drawer opens when fixture includes drift

Fixture:

- use a seeded workflow with:
  - unequal status complexity
  - at least one conditional branch
  - at least one return branch
  - multiple validators on one status
  - repeated validator ID on different statuses to verify key
    disambiguation
  - JIT prompt
  - artifact declarations
  - drift finding

Targeted verification:

```sh
cd web && npm run test:e2e -- workflow
```

Commit: `Add workflow territory E2E coverage`

## Phase 7 - Stale Vocabulary And Cleanup

Goal: remove old workflow UI and stale names.

Changes:

- Delete old card components that only supported peer-node graph mode.
- Delete old `WorkflowsPanel` tests.
- Remove stale coverage of legacy canvas fields.
- Add stale-name tests for workflow semantic vocabulary:
  - no `stations:` in workflow templates or tests
  - no `fires_on_station`
  - no `wired_to_station`
  - no `wired_from_station`
  - no `WorkflowYamlStation`
  - no `StationCard`
- Allow "station" only in explicitly non-workflow contexts if any exist.

Targeted verification:

```sh
uv run pytest -q tests/unit/internal/test_module_hygiene.py
cd web && npm test -- src/__tests__/features/workflow
```

Commit: `Remove legacy workflow graph vocabulary`

## Final Verification

Run before final push/CI monitoring:

```sh
uv run ruff check src tests
uv run pytest -q
cd web && npm run lint
cd web && npm test
cd web && npm run build
cd web && npm run test:e2e
```

If any command is too broad or slow in practice, record the targeted
substitute and why. Do not claim full verification if a full command did
not run.

## Risk Register

| Risk | Mitigation |
|------|------------|
| `station -> status` rename breaks many tests at once | Land schema/runtime/API/frontend in separate commits with targeted tests |
| UI becomes another graph | Require status regions as the only top-level visual unit |
| `workflow.yaml` becomes too weak to render artifacts | Extend schema for artifacts before writing frontend artifact UI |
| Branch routing gets overdesigned | Use structural branch classes only in v0.9.6 |
| Old API fields linger | Add stale-field route tests and TypeScript type cleanup |
| E2E flakes on dev server | Reuse existing web E2E server setup and fail on console warnings deterministically |
| Prompt body treatment gets confused with secrecy | Drawer/progressive disclosure language stays comprehension-first |

## Done Definition

This work is done when:

- `workflow.yaml` uses `statuses:` and declares artifacts
- backend schema, runtime, events, drift, API, docs, and tests use status
  vocabulary
- frontend renders one territory map from `workflow.yaml`
- gate clusters, JIT prompts, artifacts, branches, and drift each have
  distinct UI representations
- unit and E2E tests cover the map and catch console warnings
- stale workflow graph fields and station vocabulary are removed
- full final verification has run or any skipped command is explicitly
  documented
