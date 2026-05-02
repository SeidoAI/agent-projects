# v0.9.6 Workflow Process Map Revision Plan

**Date:** 2026-05-02

**Philosophy:** `docs/philosophy/workflow.md`

This plan revises the first Workflow territory implementation. The first pass
correctly moved workflow data toward `workflow.yaml`, grouped controls, and
placed proof below statuses. It failed the product intent by flattening the map
into a mostly linear status strip.

The next revision should render a routed process graph over shaded status
territory.

## Objective

Replace the current linear Workflow page with a process map that shows:

- every workflow defined by Tripwire, not only `coding-session`
- status regions as light territory behind the process
- route segments and arrows between, within, and back across status regions
- actor-coded routes for `pm-agent`, `coding-agent`, and `code`
- loops, return paths, pause/resume paths, and terminal sinks
- commands as invocation points
- gate clusters, JIT prompts, prompt checks, and validators at the moment they
  exert force
- emitted artifacts below the route/status where they are produced
- skill sources, including `SKILL.md` files, where they are loaded or relied on

## Design Correction

The UI should not be a generic graph, and it should not be a status row.

It should be:

```text
+---------------------------------------------------------------+
| NORTH: control, commands, gates, JIT prompts, skills          |
|                                                               |
| shaded status territory: planned | queued | executing | ...   |
|     routes/arrows cross, loop, branch, and hand off actors    |
|                                                               |
| SOUTH: artifacts, logs, generated proof, emitted outputs      |
+---------------------------------------------------------------+
```

Statuses are the map layer. Routes are the process. Mechanisms attach to routes
or borders. Artifacts are proof.

## Schema Direction

Move `workflow.yaml` from status-local `next` as the only topology to explicit
routes.

Target shape:

```yaml
workflows:
  coding-session:
    statuses:
      - id: planned
      - id: queued
      - id: executing
      - id: in_review
      - id: verified
      - id: completed
        terminal: true

    routes:
      - id: session-create
        actor: pm-agent
        command: pm-session-create
        trigger: command.pm-session-create
        from: source:issue
        to: planned
        controls:
          prompt_checks: [pm-session-create]
          validators: [v_workflow_well_formed, v_uuid_present]
        skills:
          - project-manager
        emits:
          artifacts:
            - id: session-yaml
              label: session.yaml

      - id: planned-to-queued
        actor: pm-agent
        command: pm-session-queue
        trigger: command.pm-session-queue
        from: planned
        to: queued
        controls:
          prompt_checks: [pm-session-queue]
          validators: [v_session_issue_coherence]

      - id: review-changes-requested
        actor: pm-agent
        command: pm-session-review
        trigger: review.outcome == changes_requested
        from: in_review
        to: executing
        kind: return
```

Rules:

- `statuses` define territory.
- `routes` define movement.
- `routes[*].from` and `routes[*].to` are canonical for topology.
- `source:*` and `sink:*` are boundary ports.
- `actor` is required for every route.
- `command` is present when a route is invoked by a PM or CLI command.
- `controls` attach validators, prompt checks, and JIT prompts to a route.
- `skills` attach instruction sources to a route.
- `emits` describes status changes, events, artifacts, comments, PR actions, or
  other outputs.

Do not preserve a second hidden topology in code. If `next` remains temporarily
for migration inside this branch, tests must prove the renderer and API use
routes as the source of truth before the branch is done.

## Workflows To Model

Add or model these workflows in the default `workflow.yaml`:

- `coding-session`: issue/session execution from planned to completed.
- `pm-session-management`: create, check, queue, spawn, monitor, review,
  complete.
- `pm-review`: PR/project review, approve, request changes, file follow-ups.
- `pm-scoping`: project scoping from raw intent to scoped issues/sessions.
- `pm-triage`: process inbound suggestions, comments, agent messages, and bugs.
- `pm-incremental-update`: surgical edit, issue close, rescope.
- `project-maintenance`: validate, lint, graph, agenda, status, project sync.

Read-only PM commands still belong in the process definition. They are route or
overlay invocations that inspect state without changing status.

## Skill Sources

Expose these skills in the workflow definition and API:

- `project-manager`: `src/tripwire/templates/skills/project-manager/SKILL.md`
- `backend-development`: `src/tripwire/templates/skills/backend-development/SKILL.md`
- `agent-messaging`: `src/tripwire/templates/skills/agent-messaging/SKILL.md`
- `verification`: `src/tripwire/templates/skills/verification/SKILL.md`

The UI should render skills as north-side instruction sources attached to actor
routes. A skill is not a status and not a route destination.

## Frontend Direction

Replace the current flex row territory renderer with a route-based map.

Target component split:

```text
WorkflowMap
  WorkflowMapToolbar
  WorkflowProcessMap
    StatusTerritoryLayer
    RouteLayer
      ActorRoute
      RouteArrow
      LoopRoute
      BoundaryPort
    ControlLayer
      GateCluster
      JitPromptMarker
      CommandInvocation
      SkillSource
    EvidenceLayer
      ArtifactMarker
      EmittedOutputMarker
    WorkflowDrawer
```

Visual grammar:

- Status territories are low-contrast background regions.
- Routes are the primary foreground shape.
- Route color or stroke style encodes actor.
- Return and loop routes curve visibly.
- Terminal routes exit to sinks.
- Commands appear as invocation markers on routes.
- Gate clusters sit on route crossings or command-triggered boundaries.
- JIT prompts use a distinct intervention marker.
- Skills sit north of the route and connect down to the route segment that loads
  them.
- Artifacts sit south of the route/status where they are produced or consumed.

Remove the redundant textual `forward` label. Direction is encoded by arrows.

## Backend And API Direction

Update the workflow backend to expose:

- workflows
- statuses
- routes
- actor metadata
- command metadata
- control registry
- skill registry
- artifacts/emitted outputs
- drift findings

The API should still be a direct interpretation of `workflow.yaml`. It can join
registry metadata, but it must not invent a second workflow language.

Required route fields in API:

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

## Implementation Phases

### Phase 1 - Route Schema

- Extend workflow schema with `routes`.
- Add actor enum or validation for `pm-agent`, `coding-agent`, and `code`.
- Add `controls`, `skills`, and `emits` shapes.
- Add validation for unknown status refs, unknown controls, unknown skills, and
  dangling source/sink refs.
- Add stale-schema tests so a workflow with only implicit status `next` cannot
  pass as the full process map source of truth.

### Phase 2 - Default Workflow Coverage

- Expand `src/tripwire/templates/workflow.yaml.j2`.
- Add the PM command workflows listed above.
- Map each command template to a workflow route.
- Map PM command prompt-check invocations to the route that invokes them.
- Map built-in JIT prompts to completion/review/escalation routes.
- Map all validator groups to route controls.
- Map all `SKILL.md` files to routes that load or depend on them.

### Phase 3 - Project Workflow Update

- Update `/Users/maia/Code/seido/tripwire/projects/project-tripwire-v0/workflow.yaml`
  to match the default schema.
- Verify that drift is zero for declared controls, commands, and skills.
- Keep unrelated project repo working-tree noise out of the commit.

### Phase 4 - Workflow API

- Expose routes, commands, actors, controls, skills, and emitted outputs.
- Keep registry joins shallow.
- Add route drift findings for:
  - unknown status
  - unknown command
  - unknown skill
  - unknown validator
  - unknown JIT prompt
  - unknown prompt check
  - route with no actor
  - route with neither source nor target

### Phase 5 - Process Map Renderer

- Replace the status-strip renderer.
- Render status territories as shaded regions.
- Render SVG route paths over the territories.
- Encode actor in route styling.
- Render loops and return routes as curved paths.
- Render command, gate, JIT prompt, skill, and artifact markers.
- Keep drawers for detail.
- Preserve keyboard access and responsive behavior.

### Phase 6 - Tests

Add frontend unit coverage for:

- non-linear routes
- return routes
- loop routes
- actor-coded routes
- command invocation markers
- skill source markers
- gate clusters attached to routes
- JIT prompt markers attached to routes
- artifact markers below routes/statuses
- no duplicate React keys
- no console warnings/errors

Add backend coverage for:

- route schema parsing
- command/skill/control validation
- workflow API route payloads
- drift findings for missing route metadata
- fresh `tripwire init` route coverage

Add Playwright coverage for:

- workflow page nonblank render
- no console warnings/errors
- actor legend visible
- at least one PM route, coding-agent route, and code route visible
- at least one loop or return route visible
- command drawer opens
- skill drawer opens
- gate, JIT prompt, and artifact drawers still open

## Acceptance Criteria

- The Workflow page is no longer a linear status strip.
- The user can see the main flow, loops, returns, and side paths.
- Route arrows are actor-coded.
- Status regions are shaded territories behind the graph.
- PM commands are visible in the map and defined in `workflow.yaml`.
- JIT prompts and prompt checks are shown at their invocation points.
- `SKILL.md` sources are visible and inspectable.
- Default `workflow.yaml` covers Tripwire PM actions as well as coding sessions.
- `project-tripwire-v0/workflow.yaml` matches the new default coverage.
- E2E tests would fail on the old linear-only implementation.

## Verification

Run targeted checks after implementation phases:

```sh
uv run pytest -q tests/unit/core/test_workflow_schema.py tests/ui/services/test_workflow_service.py
uv run pytest -q tests/integration/test_init.py
cd web && npm test -- src/__tests__/features/workflow
cd web && npm run test:e2e -- workflow
```

Final verification before push:

```sh
uv run ruff check src tests
uv run pytest -q
cd web && npm run lint
cd web && npm test
cd web && npm run build
cd web && npm run test:e2e
```
