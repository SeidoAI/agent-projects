# Workflow as Territory

This document captures the design philosophy for the next Workflow page. It is
not the implementation spec. Its job is to set the mental model, vocabulary, and
design tests that the spec should satisfy.

## Thesis

A workflow map is a territory of state regions, transition borders, control
pressure above, and material proof below, with optional overlays for runtime
traces, drift, and failure heat.

Show the lifecycle as a territory first. Then place each mechanism where it
exerts force.

The stage region is the unit. Transitions are borders. Gates are locks on
borders. JIT prompts are interventions. Artifacts are evidence shelves.
Sources and sinks are boundary ports.

## Not A Generic Graph

The Workflow page should not default to a generic node-link graph. A graph treats
statuses, gates, prompts, artifacts, and sinks as peer objects, which creates
false equivalence and false sequencing.

The user needs to understand the shape of work before they inspect the
mechanics. The page should answer:

- Where is work in the lifecycle?
- What boundary is it trying to cross?
- What pressure acts on it there?
- What evidence exists at that point?
- Where is the system drifting from the intended workflow?

## Cardinal Directions

The map needs stable directions. Without them, the page becomes a diagram of
implementation details rather than a territory a user can learn.

### West And East

West is upstream work: intent, preparation, unresolved inputs, and work that is
not yet fully committed.

East is progress through commitment: readiness, execution, review,
verification, and closure.

The default west-to-east axis is:

```text
intent -> readiness -> execution -> review -> verification -> closure
```

East does not mean "better" in an abstract sense. It means the work has crossed
more lifecycle boundaries and carries more durable commitments.

### North And South

North is control pressure: governance, policy, gates, validators, role
requirements, JIT prompts, and anything that constrains or interrupts movement.

South is material proof: artifacts, logs, produced documents, outputs, and the
evidence that makes progress auditable.

```text
                  CONTROL / GOVERNANCE
            gates, prompts, checks, policy

WEST    intent | readiness | execution | review | verified | closed    EAST

              artifacts, logs, outputs, evidence
                    MATERIAL / PROOF
```

This gives every object a reason to live where it lives.

## State Regions

Statuses should be regions, not nodes.

A status is a condition work is inside. A status change is a transition across a
region boundary. Treating statuses as nodes makes state look like an event and
makes the map feel like an execution trace instead of a stable model.

A region should answer:

- What does this state mean?
- What moves work into it?
- What can happen while work is here?
- What allows work to leave?

Runtime events can draw traces across regions. They should not replace the
regions.

## One Unit Of Space

One unit of visual space should be a stage region, not an individual mechanism.
The region can have three layers:

```text
+------------------------------------------------------+
| control shelf: gate clusters, JIT prompts, policy    |
|                                                      |
| stage body: state meaning, allowed movement, focus   |
|                                                      |
| evidence shelf: artifacts, logs, outputs, proof      |
+------------------------------------------------------+
```

Transitions live between stage regions. A transition is a border crossing.

Gates belong on borders because they decide whether work can cross. JIT prompts
belong at the moment they interrupt or reinforce. Artifacts belong in the
evidence shelf because they are produced or consumed proof. Sources and sinks
belong outside the main lifecycle as system boundary ports.

## Gates

Gates should usually be grouped. If several validators or checks run at the same
station or transition, the user experiences them as one checkpoint, not as a row
of unrelated peer nodes.

A gate cluster can show:

- how many checks run there
- which checks are blocking
- whether the checkpoint is advisory or mandatory
- recent pass/fail state when runtime data is available
- the most important labels without exposing full rule prose by default

Individual checks should be available through expansion or a drawer. They should
not dominate the first read.

## JIT Prompts

JIT prompts are not gates. A gate decides whether work can cross a boundary. A
JIT prompt injects attention at a specific moment.

The visual grammar should make this difference obvious. A JIT prompt should feel
like an intervention pinned to a stage or transition: the agent is interrupted,
reminded, or given context at the moment recency matters.

Prompt details, especially sensitive prompt bodies, should be progressively
revealed. PM mode may reveal content that normal runtime views should keep
hidden.

## Artifacts

Artifacts should not look like workflow steps. They are proof objects.

They should sit in or below the region where they are produced, consumed, or
required. Their default role is to answer: what durable evidence exists at this
point in the workflow?

## Sources And Sinks

Sources and sinks are boundary ports, not ordinary lifecycle states.

A source brings work into the map. A sink removes work from the map or hands it
to another system. They should be visually peripheral so they explain the system
boundary without competing with the main lifecycle.

## Pressure And Contours

The base map should be two-dimensional and instantly readable. The meaning is
three-dimensional: the third dimension is pressure.

Pressure can be encoded without making the page literally 3D:

- more validators make a transition gate thicker or denser
- more JIT prompts make an intervention marker stronger
- more artifacts make the evidence shelf heavier
- more drift or failures warm the region or border
- more human involvement strengthens the review boundary

Contour lines answer: how hard is this area to cross?

## Visual Hierarchy

The first read should be:

1. lifecycle regions
2. transitions between regions
3. exit gates and blockers
4. prompts and artifacts attached to those moments
5. peripheral sources and sinks
6. detailed rule bodies only on demand

The current risk is showing every implementation object at once. The better
model is to show structure first, pressure second, detail third.

## Progressive Disclosure

The default view should avoid rule prose, long names, full prompt text, and every
validator as a large visual object.

The default view should show enough to understand counts and importance:

- this transition has three blocking checks
- this stage emits one artifact
- this event fires two JIT prompts
- this workflow has one conditional branch

Details should appear through interaction:

- hover for compact explanation
- click for a drawer with full metadata
- expand a cluster to reveal member checks
- PM mode to reveal sensitive prompt bodies

## Overlays

The base map is the definition of the workflow. It should support overlays
without changing the underlying grammar.

Useful lenses include:

- Definition: what is supposed to happen?
- Runtime: what happened recently?
- Drift: where does implementation disagree with definition?
- Quality: where does work tend to fail, loop, stall, or require intervention?

Status regions remain stable. Runtime events draw traces over the map. Drift and
failure heat color the territory.

## Additional Dimensions

The spec should preserve these distinctions:

- State vs time: where work is differs from what happened.
- Nominal vs exceptional flow: the happy path should dominate, while retries,
  blocked paths, escalation, pause states, and off-track states remain visible as
  side routes.
- Ownership: agent-owned, PM-owned, and system-owned areas may need subtle
  lane or shading treatment.
- Zoom level: zoomed out shows regions and checkpoints; mid-level shows named
  gate, prompt, and artifact clusters; detail level shows rules, prompt bodies,
  recent runs, and drift.
- Semantic stability: the grammar should survive coding sessions, PM review,
  inbox handling, concept freshness, release workflows, and future workflow
  types.

## Design Tests

The future Workflow page should pass these tests:

- Can a user trace the main lifecycle from west to east in five seconds?
- Can a user tell what state work is in without reading implementation labels?
- Can a user distinguish a state from a status change?
- Can a user see what blocks a transition?
- Can a user tell the difference between a gate and a JIT prompt?
- Can a user find the proof produced by a stage?
- Can a user understand sources and sinks as boundaries, not peer stages?
- Can the page reveal detail without making the default view dense?
- Can runtime events, drift, and quality signals be overlaid without changing
  the base grammar?

## Spec Implications

The spec should start from the territory model, not from the current component
tree.

It should define:

- the stage-region layout
- the west-to-east lifecycle axis
- the north/south control/proof shelves
- grouped transition gates
- unique visual treatments for gates, JIT prompts, artifacts, sources, and sinks
- the drawer and expansion model
- the overlay model for runtime, drift, and quality data

The product should feel less like a dependency graph and more like an operating
map for agentic work.
