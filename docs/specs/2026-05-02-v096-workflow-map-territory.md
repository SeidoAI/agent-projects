# v0.9.6 - Workflow Map territory revamp

**2026-05-02**

This spec implements the philosophy in
`docs/philosophy/workflow.md`: Workflow is a territory of status
regions, transition borders, control pressure, and proof. It replaces
the current split view where the UI renders both an introspection
canvas and a separate `workflow.yaml` panel.

The canonical source is `workflow.yaml`. The UI must adapt to that file,
not to hardcoded lifecycle assumptions.

## Goals

- Make the Workflow page explain the process as a map, not as a generic
  graph of peer objects.
- Rename the workflow vocabulary from `station` to `status` across the
  codebase.
- Treat status regions as the primary visual unit.
- Treat validators as gates on attempted status changes.
- Group concurrent validators and checks into transition gate clusters.
- Treat JIT prompts as intervention markers, not gates.
- Derive expected artifacts from `workflow.yaml`.
- Show static process complexity as pressure. Do not turn the map into
  a live monitor in this release.
- Add tests that catch duplicated React keys, console warnings, blank
  workflow pages, and stale vocabulary.

## Non-Goals

- No runtime failure heat map in v0.9.6.
- No live per-session monitor state on the Workflow page.
- No second backend "territory DTO" that becomes another workflow
  language.
- No backwards-compatible `stations:` alias in `workflow.yaml`.
- No legacy canvas plus new panel coexistence. The page should render one
  coherent map.

## Canonical Source

`workflow.yaml` is the source of truth for process shape.

The backend may parse, validate, and expose the file through the API. It
must not invent a second interpretive model. The frontend should be able
to look at the API payload and see the same concepts that exist in
`workflow.yaml`.

The API can include registry metadata for referenced IDs, such as
validator names and descriptions. That is metadata joining, not a second
workflow model.

## Vocabulary

Retire `station` for workflow semantics. Use `status`.

| Old | New | Meaning |
|-----|-----|---------|
| station | status | A condition work can be in |
| station card | status region | The visual territory for one status |
| next station | next status | Target status for a transition |
| validators at station | entry gates for status | Checks triggered by attempted status change |
| station registry | status registry | Lookup of controls attached to a workflow status |

Keep "status" concrete. Do not rename it to an abstract term such as
"commitment state" until the product needs that distinction.

## Workflow Schema

Hard migrate `workflow.yaml` from `stations:` to `statuses:`.

```yaml
workflows:
  coding-session:
    actor: coding-agent
    trigger: session.spawn
    statuses:
      - id: planned
        next: queued
        artifacts:
          produces:
            - id: plan
              label: plan.md

      - id: queued
        next: executing

      - id: executing
        next: in_review
        artifacts:
          produces:
            - id: diff
              label: staged diff

      - id: in_review
        next:
          - if: review.outcome == approved
            then: verified
          - if: review.outcome == changes_requested
            then: executing
          - else: paused
        validators:
          - artifact-presence
          - workflow-well-formed
        jit_prompts:
          - self-review
        prompt_checks:
          - pm-session-review
        artifacts:
          produces:
            - id: review-notes
              label: review notes

      - id: verified
        next: completed

      - id: completed
        terminal: true
        artifacts:
          produces:
            - id: session-signature
              label: session signature
```

### Status Controls

Controls declared on a status are entry controls for attempts to enter
that status unless a later spec introduces explicit transition-local
controls.

This matches the Tripwire runtime model: the agent attempts a status
change; `tw validate` and the review/merge path determine whether that
change is allowed to become ground truth on main.

For example:

```yaml
- id: in_review
  validators: [artifact-presence, workflow-well-formed]
```

means: when work attempts to enter `in_review`, these validators gate
the boundary into `in_review`.

### Artifacts

Expected artifacts are declared in `workflow.yaml`.

Do not hardcode lifecycle artifacts in the UI. Do not derive expected
artifacts from live session files. Live files are evidence that a
specific run produced something; `workflow.yaml` defines what the
process expects.

Initial artifact shape:

```yaml
artifacts:
  produces:
    - id: plan
      label: plan.md
      path: sessions/{session_id}/plan.md
  consumes:
    - id: issue
      label: issue brief
```

`path` is optional in v0.9.6. The map needs stable IDs and labels first.

## Map Grammar

The map uses three bands:

```text
                 CONTROL / GOVERNANCE
          gate clusters, JIT prompts, prompt checks

WEST   planned | queued | executing | in_review | verified | completed   EAST

              artifacts, logs, outputs, proof
                   MATERIAL / PROOF
```

### Status Regions

A status region is the base unit of visual space.

Status regions do not need equal width. More complex statuses can take
more visual acreage. Complexity is static process complexity, not live
runtime health.

Factors that can increase visual weight:

- number of validators
- number of JIT prompts
- number of prompt checks
- number of expected artifacts
- conditional branches
- number of incoming or outgoing transitions

The layout must preserve west-to-east lifecycle direction even when
status regions have unequal width.

### Transition Borders

A transition is a border crossing from one status to another.

Render transitions as roads or borders between status regions, not as
nodes. The user should read "work crosses this boundary" rather than
"there is another thing in the graph".

### Gate Clusters

Validators and prompt checks that run for the same attempted status
change are grouped into one gate cluster.

The default gate cluster display shows:

- count of validators
- count of prompt checks
- whether any control blocks progress
- short labels for the most important controls when space allows

The drawer shows the full member list and metadata.

### JIT Prompts

JIT prompts are interventions.

They should look visually different from gate clusters. A JIT prompt
marker should feel like the system interrupts or reminds the agent at a
specific point in the process.

Prompt body text is not hidden because it is sensitive. It is hidden by
default because full detail destroys the map. Reveal it through the
drawer or an expansion control. If role-based redaction remains for
other product reasons, treat it as orthogonal to the map grammar.

### Artifacts

Artifacts are proof objects.

Render produced artifacts in the south shelf of the status that
produces them. Render consumed artifacts as incoming proof requirements
where helpful, but do not let artifacts become peer workflow steps.

### Sources And Sinks

Sources and sinks are boundary ports.

They live outside the main west-to-east lifecycle. They explain where
work enters and leaves the workflow without competing with statuses.

## Branches

Branches are routes, not statuses.

Render a single `next: <status>` as the main road eastward when it moves
forward through the lifecycle.

Render conditional `next:` as alternative routes leaving the same
status boundary:

- the dominant or happy-path branch stays visually calm and direct
- return branches bend west
- terminal branches exit into a sink or terminal boundary
- exceptional branches sit as side routes

Classification can be structural in v0.9.6:

- target to the right: forward branch
- target to the left: return branch
- target terminal: terminal branch
- target not on the main west/east path: side branch

Do not make every branch visually equal unless the workflow definition
requires equal weighting.

## Pressure

Pressure is static process complexity.

For v0.9.6, pressure is derived from the workflow definition, not from
runtime event counts or historical failures.

Pressure may affect:

- status region width
- gate cluster density
- border thickness
- marker count badges
- label priority

Pressure must not imply that a process is currently unhealthy. That is a
monitoring concern, not the initial Workflow page concern.

## Overlays

Ship these overlays:

1. **Definition**: the base map from `workflow.yaml`.
2. **Complexity**: static pressure derived from validators, JIT prompts,
   prompt checks, artifacts, and branches.
3. **Drift**: definition integrity findings, such as unknown controls,
   dangling next statuses, stale registered controls, or mismatched
   status vocabulary.

Do not ship runtime failure heat or quality heat in this revamp. Those
belong to a later monitor-oriented view or overlay once the base map is
stable.

## API Contract

Replace the dual legacy shape with a workflow-first response.

```ts
interface WorkflowResponse {
  project_id: string;
  workflows: WorkflowDefinition[];
  registry: WorkflowRegistry;
  drift: WorkflowDriftSummary;
}

interface WorkflowDefinition {
  id: string;
  actor: string;
  trigger: string;
  statuses: WorkflowStatus[];
}

interface WorkflowStatus {
  id: string;
  label?: string;
  description?: string;
  next: WorkflowNext;
  validators: string[];
  jit_prompts: string[];
  prompt_checks: string[];
  artifacts: WorkflowStatusArtifacts;
}

type WorkflowNext =
  | { kind: "single"; single: string }
  | { kind: "conditional"; branches: WorkflowBranch[] }
  | { kind: "terminal" };

type WorkflowBranch =
  | { if: string; then: string }
  | { else: string };

interface WorkflowStatusArtifacts {
  produces: WorkflowArtifactRef[];
  consumes: WorkflowArtifactRef[];
}

interface WorkflowArtifactRef {
  id: string;
  label: string;
  path?: string;
}

interface WorkflowRegistry {
  validators: RegistryEntry[];
  jit_prompts: RegistryEntry[];
  prompt_checks: RegistryEntry[];
}

interface RegistryEntry {
  id: string;
  label: string;
  description?: string;
  blocking?: boolean;
}

interface WorkflowDriftSummary {
  count: number;
  findings: WorkflowDriftFinding[];
}
```

`registry` exists so the frontend can render names and drawers for
referenced IDs. The canonical topology still comes from
`workflows[*].statuses`.

Remove or deprecate these legacy API fields in the same branch:

- `lifecycle.stations`
- `validators[*].fires_on_station`
- `jit_prompts[*].fires_on_station`
- `connectors.sources[*].wired_to_station`
- `connectors.sinks[*].wired_from_station`
- hardcoded `_LIFECYCLE_ARTIFACTS`

Because this project prefers hard migrations, do not keep old response
fields unless an active caller outside this repo requires them.

## Frontend Design

Replace the current `WorkflowMap` canvas plus `WorkflowsPanel` with one
territory renderer.

Suggested component split:

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

### Default View

Default view shows:

- status regions
- transitions
- gate cluster counts
- JIT prompt intervention markers
- artifact chips
- source/sink ports
- drift indicators when present

Default view does not show:

- full validator prose
- full prompt bodies
- every validator as a peer card
- runtime event rows
- live failure counts

### Drawer

Clicking a gate cluster opens a drawer with:

- transition or target status
- validators
- prompt checks
- blocking/advisory labels
- registry descriptions

Clicking a JIT prompt marker opens:

- prompt ID and label
- event or status-change moment
- prompt body
- ack/blocking metadata if present

Clicking an artifact opens:

- artifact ID
- label
- producing status
- consuming status, if any
- path, if declared

Clicking drift opens:

- finding code
- status/workflow affected
- message
- suggested repair, if available

### Responsive Behavior

Desktop gets the full territory.

Narrow viewports can stack statuses vertically while preserving the same
grammar:

- top becomes control shelf
- middle becomes status body
- bottom becomes evidence shelf
- transitions become vertical connectors

Do not shrink text with viewport width. Use fewer visible labels and
progressive disclosure instead.

## Migration Plan

Run a targeted grep and update every workflow-semantic use of station:

```sh
rg -n "\bstation\b|\bstations\b|Station|Stations|__tripwire_workflow_station__|fires_on_station|wired_to_station|wired_from_station|from_station|to_station|unknown_next_station|duplicate_station_id" src tests web docs
```

Expected migration areas:

- `docs/specs/2026-04-30-v09-workflow-substrate.md`
- `src/tripwire/core/workflow/schema.py`
- `src/tripwire/core/workflow/loader.py`
- `src/tripwire/core/workflow/registry.py`
- `src/tripwire/core/workflow/transitions.py`
- `src/tripwire/core/validator/checks/workflow.py`
- workflow event schema and event emission call sites
- workflow drift code and finding codes
- JIT prompt `at = ("workflow", "status")` declarations
- validator registration metadata
- prompt-check frontmatter and collection code
- `src/tripwire/ui/services/workflow_service.py`
- `web/src/lib/api/endpoints/workflow.ts`
- `web/src/features/workflow/*`
- workflow frontend tests
- workflow backend tests
- fixtures and `workflow.yaml.j2`

Use hard migration:

- `workflow.yaml` uses `statuses:`, not `stations:`.
- event payloads use `status`, `from_status`, and `to_status`.
- finding codes use `status`, for example
  `workflow/duplicate_status_id` and `workflow/unknown_next_status`.
- TypeScript types use `WorkflowStatus`, not `WorkflowYamlStation`.
- React components use `StatusRegion`, not `StationCard`.

Only preserve "station" where it is not workflow vocabulary.

## Test Plan

### Python

- Schema tests parse `statuses:` and reject stale `stations:`.
- Loader tests cover single, conditional, and terminal `next` under
  statuses.
- Well-formedness tests use status-based finding codes.
- Registry tests expose `known_*_ids` and `*_for_status` APIs.
- Transition tests emit `status`, `from_status`, and `to_status`.
- Drift tests report status vocabulary and dangling status refs.
- Route tests assert `/api/projects/{pid}/workflow` returns the new
  workflow-first shape and no legacy lifecycle canvas fields.

### Frontend Unit Tests

- WorkflowMap renders one territory, not canvas plus YAML panel.
- Status regions render as regions with control/evidence shelves.
- Gate clusters group validators by attempted status change.
- JIT prompts render as intervention markers, not gate cards.
- Artifacts render from workflow-derived declarations.
- Conditional branches render as routes.
- No duplicate React keys for repeated validator IDs or repeated
  controls across statuses.
- Unexpected `console.warn` and `console.error` fail tests.

### E2E

Use Playwright against a seeded project:

- `/p/:projectId/workflow` renders nonblank.
- no console warnings/errors, including duplicate key warnings.
- the main lifecycle can be found by accessible region labels.
- gate cluster, JIT prompt marker, artifact chip, and drift indicator
  each open a drawer.
- screenshot smoke on desktop and mobile.

## Acceptance Criteria

- The codebase no longer uses `station` for workflow semantics.
- `workflow.yaml` uses `statuses:` and declares artifacts.
- `/api/workflow` exposes workflow definitions with statuses and
  registry metadata.
- The Workflow page has one coherent territory renderer.
- Validators are grouped into transition gate clusters.
- JIT prompts have a distinct intervention visual.
- Artifacts come from workflow declarations.
- Static complexity affects visual emphasis without implying live
  health.
- Drift remains a definition-integrity overlay.
- Unit and E2E tests fail on duplicate keys, console warnings, blank
  workflow render, stale `station` vocabulary, and missing drawer
  interactions.

## Implementation Order

1. Rename schema and fixtures from `stations` to `statuses`.
2. Rename backend workflow registry, transitions, event fields, and
   drift codes.
3. Add artifact declarations to `workflow.yaml` and expose them through
   the workflow API.
4. Replace the API response with workflow-first `statuses` plus registry
   metadata.
5. Replace the current WorkflowMap canvas/panel split with the territory
   renderer.
6. Add frontend unit tests and Playwright coverage.
7. Remove stale legacy workflow fields and component names.
