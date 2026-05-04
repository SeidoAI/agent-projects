# Workflow Page Frontend Handoff

Date: 2026-05-03

Audience: frontend engineer taking over the Workflow page.

Status: the current v0.9.6 implementation should be treated as a prototype, not
as the target UI. It moved useful data into `workflow.yaml`, but the frontend
does not yet express the product idea.

## Read These First

- `docs/philosophy/workflow.md`
- `docs/specs/2026-05-02-v096-workflow-map-territory.md`
- `docs/plans/2026-05-02-v096-workflow-process-map-revision-plan.md`
- `src/tripwire/templates/workflow.yaml.j2`
- `web/src/lib/api/endpoints/workflow.ts`
- `web/src/features/workflow/WorkflowMap.tsx`
- `web/src/features/workflow/useWorkflowLayout.ts`
- `web/src/features/workflow/WorkflowDrawer.tsx`

## Executive Summary

The Workflow page should be an operating map for agentic work.

It should not be a generic graph, a monitor, or a linear status checklist. The
core model is: status territory underneath, process routes over it, controls
above, proof below. Statuses are regions. Routes are movement. Gates are locks
on transitions. JIT prompts are interventions. Commands are invocation points.
Skills are instruction sources. Artifacts are proof. Actors own route segments.

The current frontend misses this. It renders a horizontally scrolling status
strip with route labels and marker badges. That is closer to a dressed-up
timeline than a process map. It does not make loops, returns, PM workflows,
actor handoffs, or skill loading feel structurally important. A frontend engineer
should feel free to replace the Workflow map renderer rather than polishing the
existing one.

## What We Discussed

### 1. The mental model is a map

Think of a territory map:

- West means intent, preparation, unresolved inputs, and upstream work.
- East means increasing commitment: readiness, execution, review, verification,
  closure.
- North means control pressure: gates, validators, prompt checks, JIT prompts,
  commands, skills, policy.
- South means material proof: artifacts, logs, outputs, generated documents,
  evidence.

This creates a stable grammar:

```text
+---------------------------------------------------------------+
| NORTH: commands, gates, JIT prompts, prompt checks, skills    |
|                                                               |
| WEST: intent -> readiness -> execution -> review -> closure   |
|       shaded status regions with routes/arrows crossing them  |
|                                                               |
| SOUTH: artifacts, logs, emitted outputs, proof                |
+---------------------------------------------------------------+
```

### 2. Statuses are regions, not nodes

A status is a condition work is inside. A status change is a border crossing.
If statuses are rendered as peer nodes beside validators, prompts, commands, and
artifacts, the UI creates false equivalence.

Use statuses as lightly shaded background regions. They should establish the map
territory. The routes should be the primary foreground.

### 3. The flow is graph-like, but not a generic graph

The page still needs arrows and graph flow. The user must see:

- main lifecycle routes
- return paths
- loops
- pause/resume or blocked paths
- terminal sinks
- source ports
- actor handoffs

But the graph is routed over status territory. It is not a free-floating
node-link graph where every object has equal visual weight.

### 4. The page is a process definition first, not a monitor

The default view should show what is supposed to happen according to
`workflow.yaml`.

Do not start with:

- live failure counts
- recent validator failures
- session health
- runtime heat maps

Those can become overlays later. For v0.9.6, show static process complexity:
how many gates, prompts, commands, skills, branches, and artifacts exist in the
definition.

Drift belongs on the page, but drift means definition integrity: implementation
and workflow definition disagree. It is not a live health score.

### 5. `workflow.yaml` is canonical

The UI should derive from `workflow.yaml` through the existing API. Avoid adding
a second backend "territory DTO" that becomes another workflow language.

The backend can parse, validate, and join registry metadata. It can expose
labels, descriptions, paths, and blocking/advisory flags. But the topology should
come directly from `workflow.yaml`:

- workflows
- statuses
- routes
- route actors
- route commands
- route controls
- route skills
- route emits

If the YAML cannot be interpreted into a good map, improve the YAML schema
rather than hiding that problem behind an opaque backend layout model.

## What The Existing Work Got Right

Keep these ideas:

- `workflow.yaml` now has explicit `routes`.
- `workflow.yaml` uses `statuses`, not `stations`.
- Controls are grouped under routes.
- Validators and prompt checks are gate-like.
- JIT prompts are separate from gates.
- Artifacts are shown below the process rather than as workflow steps.
- The API exposes registries for validators, JIT prompts, prompt checks,
  commands, and skills.
- The route schema can represent PM-agent, coding-agent, and code actor routes.
- Tests now catch duplicate React keys and console warnings better than before.

## What The Existing Frontend Gets Wrong

The current files are:

- `web/src/features/workflow/WorkflowMap.tsx`
- `web/src/features/workflow/useWorkflowLayout.ts`
- `web/src/features/workflow/WorkflowDrawer.tsx`

The main problems:

- The page still reads as a mostly linear row of statuses.
- Routes are not visually dominant enough to feel like the process.
- Return routes and loops do not have enough spatial drama.
- PM workflows exist in data but do not feel like part of one understandable
  system.
- The workflow selector hides the fact that Tripwire has many workflows.
- Skills are tiny badges rather than instruction sources attached to actor
  work.
- Commands are tiny badges rather than invocation points that activate routes.
- Gate, command, skill, JIT, route, and artifact markers all have similar visual
  weight.
- The "pressure" idea is reduced to small text and mildly variable region width.
- The map is inside a scroll box with a fixed canvas height, so it feels like a
  diagram clipped into a card.
- Source and sink ports are not visually meaningful.
- The route labels can be redundant. For example, do not label ordinary eastward
  movement "forward"; arrows and geometry already say that.
- The current fallback route synthesis creates weak labels like `Route queued`
  and `Route in_review`, which are not product-quality route names.

Conclusion: do not incrementally polish this renderer. Rework the visual
architecture.

## Product Requirements

The next implementation must show:

1. Every workflow, not just `coding-session`.
2. PM actions and PM commands as part of the process map.
3. Actor-coded route arrows for `pm-agent`, `coding-agent`, and `code`.
4. Light shaded regions indicating session/status territory.
5. Loops, return paths, side paths, and terminal sinks.
6. Commands as route invocation points.
7. Gate clusters at the route or boundary where checks fire.
8. JIT prompts at the moment they can fire.
9. Prompt checks and validators grouped where they exert force.
10. Artifacts and emitted outputs below the route or status where produced.
11. `SKILL.md` sources and where they are loaded or relied on.
12. Progressive disclosure through drawers, not dense default text.

## Desired Visual Hierarchy

First read:

1. shaded status territories
2. primary process routes and arrows
3. actor ownership and branch shape
4. important gates and interventions
5. commands and skill sources
6. proof/artifacts
7. drift markers
8. full details only in drawers

The map should answer these questions quickly:

- Where does work enter the system?
- Which workflow am I looking at?
- What status territory does work pass through?
- Which actor moves work at each point?
- Which command invokes this movement?
- Where can it loop or return?
- What blocks each transition?
- Which JIT prompts can intervene?
- Which skills inform the actor?
- What proof is emitted?
- Where does the workflow exit?

## Suggested UI Architecture

Replace the current renderer with a map-oriented component tree:

```text
WorkflowPage
  WorkflowHeader
  WorkflowNavigator
  WorkflowProcessMap
    StatusTerritoryLayer
      StatusRegion
    RouteLayer
      ActorRoute
      RouteArrow
      LoopRoute
      ReturnRoute
      SourcePort
      SinkPort
    ControlLayer
      CommandInvocation
      GateCluster
      JitPromptMarker
      SkillSource
    EvidenceLayer
      ArtifactMarker
      EmittedOutputMarker
    OverlayLayer
      DriftMarker
  WorkflowDrawer
```

Important: `WorkflowProcessMap` should feel like the primary workspace, not a
card embedded in a page. It can have a boundary, but avoid nested-card styling.

### StatusTerritoryLayer

Render status regions as large, quiet territories behind the process.

Guidelines:

- Use low-contrast shaded bands or zones.
- Unequal widths are acceptable and desirable where process complexity differs.
- Regions should not look like clickable cards first. They are map territory.
- Status labels should be readable but not dominate route labels.
- A status can have a subtle pressure contour or density marker.

### RouteLayer

Routes should be the dominant foreground.

Guidelines:

- Use SVG for routes and arrows.
- Encode actor through stroke color and optionally texture:
  - PM-agent route: one distinct color
  - coding-agent route: one distinct color
  - code route: one distinct color
- Use curve shape to encode route kind:
  - forward: calm eastward route
  - return: visible westward arc
  - loop: curved loop returning to same territory or earlier territory
  - side: secondary branch
  - terminal: route exiting into sink
- Make arrowheads legible.
- Do not rely on text labels to explain direction.

### ControlLayer

Controls live north of routes or on transition boundaries.

Guidelines:

- Commands are invocation points, not generic chips.
- Gate clusters should look like locks/checkpoints.
- JIT prompts should look like interventions, not locks.
- Skills should look like instruction sources connected to the routes that load
  them.
- Prompt checks and validators should be grouped by route.

### EvidenceLayer

Artifacts live south.

Guidelines:

- Artifacts are proof, not steps.
- Keep them visually quieter than routes and gates.
- Group emitted outputs by route/status.
- Avoid repeating "no declared proof" under every status; that creates visual
  noise. Empty evidence shelves can simply be blank.

### WorkflowNavigator

Because we now model more than coding sessions, do not hide workflows in a tiny
segmented control.

Options:

- A left-side workflow list with small route counts and actor mix.
- A top rail grouped by workflow family: coding, PM review, scoping, triage,
  maintenance.
- A minimap or overview that shows all workflows as territories, then opens one
  in detail.

The key is that the user should learn that Tripwire is built from multiple
workflows, not assume the page is only the coding-session lifecycle.

## Data Contract To Use

The frontend should consume:

- `workflows[*].statuses`
- `workflows[*].routes`
- `registry.validators`
- `registry.jit_prompts`
- `registry.prompt_checks`
- `registry.commands`
- `registry.skills`
- `drift.findings`

Route fields expected by the UI:

- `id`
- `workflow_id`
- `actor`
- `from`
- `to`
- `kind`
- `label`
- `trigger`
- `command`
- `controls`
- `skills`
- `emits`

Do not build UI around synthesized fallback routes. Fallbacks are useful for
defensive rendering, but the real default workflows should define route IDs,
route labels, actors, commands, skills, controls, and emits explicitly.

## Workflow Coverage Required

The map must be able to represent at least these workflows from the default
`workflow.yaml`:

- `coding-session`
- `pm-session-management`
- `pm-review`
- `pm-scoping`
- `pm-triage`
- `pm-incremental-update`
- `project-maintenance`

Read-only PM commands still belong in the process. They are route invocations or
inspection overlays, not invisible implementation details.

## Skills To Surface

At minimum, show these skill sources:

- `project-manager`
- `backend-development`
- `agent-messaging`
- `verification`

The UI should make it clear where each skill is pulled into the workflow. A
skill is not a state and not a destination. It is an instruction source attached
to an actor route.

## Interaction Model

Every visible object must be keyboard accessible.

Click or keyboard activate:

- status region: status overview drawer
- route: route drawer
- command marker: command drawer
- gate cluster: gate drawer
- JIT prompt marker: JIT prompt drawer
- skill source: skill drawer
- artifact marker: artifact drawer
- drift marker: drift drawer

Drawer content should be clear and sparse:

- what is this object?
- where does it attach?
- which actor owns it?
- what triggers it?
- what controls or emits does it have?
- where is the source file or registry item?

Avoid long educational prose in the drawer. Use labels, grouped lists, and links.

## Responsive Behavior

Desktop:

- Map can be wide.
- Status territories run west-east.
- Routes can arc and loop.
- Skills/control pressure sit north.
- Proof sits south.

Mobile:

- Do not simply shrink the canvas.
- Consider stacking status regions vertically while preserving route direction.
- Hide secondary labels, not primary structure.
- Keep drawers full-height and simple.

Do not scale font size with viewport width.

## Accessibility And Testing Requirements

This page previously had issues that good tests should have caught:

- duplicate React keys
- console warnings
- blank workflow graph
- stale accessible labels after UI changes
- favicon 404
- fallback route labels used in e2e

The next implementation needs tests that fail on those classes of errors.

### Unit Tests

Add or update frontend tests for:

- non-linear route layout
- return route layout
- loop route layout
- actor-coded route rendering
- command markers
- skill markers
- gate clusters attached to routes
- JIT prompt markers attached to routes
- artifact markers below statuses/routes
- drawers for route, command, skill, gate, JIT prompt, artifact, drift
- no duplicate keys when the same validator appears on multiple routes
- no console warning/error during render
- route labels do not depend on synthesized fallback route names

### E2E Tests

Use a seeded project with:

- at least one PM route
- at least one coding-agent route
- at least one code route
- at least one return route
- at least one loop route
- at least one command marker
- at least one skill marker
- at least one gate cluster
- at least one JIT prompt marker
- at least one artifact marker
- at least one drift marker

Playwright should assert:

- `/p/:projectId/workflow` renders nonblank
- browser console has no warnings/errors
- actor legend is visible
- PM, coding-agent, and code routes are visible
- loop or return route is visible
- command drawer opens
- skill drawer opens
- gate drawer opens
- JIT prompt drawer opens
- artifact drawer opens
- desktop screenshot smoke
- mobile screenshot smoke

## Concrete Build Plan For The Frontend Engineer

### Step 1 - Audit the current API payload

Run the dev server, load `/api/projects/{pid}/workflow`, and inspect the actual
payload for `project-tripwire-v0`.

Confirm:

- all expected workflows are present
- all routes have explicit IDs and labels
- actors are present
- commands and skills are present
- controls and emits are present
- drift is understood and not mistaken for runtime failure

If the payload lacks data needed for the UI, fix `workflow.yaml` or the shallow
API join, not the renderer.

### Step 2 - Replace layout derivation

Replace `buildWorkflowTerritory` with a real map model:

- regions
- ports
- routes
- route segments
- markers
- shelves
- bounds

Do not position all route markers at `(fromX + toX) / 2`. That creates marker
piles and weak semantics. Markers should attach to meaningful route points:

- command at route start or invocation point
- gate at boundary crossing
- JIT prompt at intervention point
- skill above route start or actor segment
- artifact below route end or emitting segment

### Step 3 - Replace the renderer

Build layers:

1. territory layer
2. route layer
3. control layer
4. evidence layer
5. overlay layer

Avoid chip soup. A chip is fine inside a drawer or compact cluster, but the map
needs shapes: territories, paths, ports, locks, interventions, evidence shelves.

### Step 4 - Redesign workflow selection

Make multi-workflow support obvious.

Do not bury workflows in a tiny top toolbar. Tripwire has a process ecosystem,
not one lifecycle. A frontend engineer should propose a navigation treatment
that lets users understand the system at a glance.

### Step 5 - Harden tests

Write tests before declaring the UI done. The old implementation passed too much
without proving it made visual sense.

At minimum, add fixture-driven tests that would fail if the page regressed to a
linear status strip.

## Acceptance Criteria

The implementation is done when a frontend engineer can open the page and say yes
to all of these:

- I can see statuses as territory, not as cards in a row.
- I can trace the main process route without reading every label.
- I can see return routes and loops.
- I can tell which actor owns each route by sight.
- I can see PM commands as part of the workflow.
- I can see where skills are loaded.
- I can tell a gate from a JIT prompt.
- I can see proof/artifacts below the process.
- I can inspect details without the default map becoming dense.
- I can switch between or understand multiple workflows.
- I do not see runtime monitor data pretending to be workflow definition.
- The page feels like an operating map, not a diagram made from implementation
  objects.

## Final Warning

The backend/schema direction is basically sound. The frontend is not.

Do not spend the next pass making the current strip prettier. Solve the map.
