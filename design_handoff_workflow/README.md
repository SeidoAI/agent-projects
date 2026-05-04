# Handoff: Tripwire Workflow Page

## What this is

The **Workflow page** is a new screen in the Tripwire dashboard. It renders the framework's six canonical workflows from `workflow.yaml` as **operating maps** — territory-and-routes flowcharts that show the lifecycle of a session, the controls that gate each transition, the agent skills that ride along, the artifacts that get produced, and the just-in-time prompts that can fire mid-execution.

This is the **V1 (territory-bands)** direction — the canonical map. Other directions were explored on the canvas; we are shipping V1.

There is no equivalent in the existing Tripwire UI. New PMs currently learn the orchestration model by reading the YAML; this screen replaces that.

## Where it lives

A new top-level route — `/{project}/workflow` — reachable from the left rail under the existing **Process** entry (or as its own item — confirm with the team). Uses the same `<ScreenShell>` chrome (left rail + top bar) as every other screen.

## About the design files

`Tripwire - Workflow.html` is a React-via-CDN prototype (Babel-in-browser) on the design-canvas component. The rendered SVG/JSX is **design reference**, not production code to copy. Recreate it in the existing frontend (`src/tripwire/ui/frontend/` — React 18 + Vite + Tailwind 4 + react-router) using the codebase's existing component patterns.

The chart itself is custom inline SVG — there is no React-flow / D3 dependency to add. Build it as a single `<WorkflowMap workflow={...} />` component; the layout function (`workflow/layout.jsx` in the mock) computes coordinates, the renderer (`workflow/flowchart.jsx`) emits SVG. Both are under 350 lines and pure functions over the workflow definition.

## Fidelity

**High-fidelity for V1 (`coding-session`).** The other five workflows render with the same primitives but are sketched, not finalised — the layout function handles them all, but per-workflow tuning (spacing for narrow workflows like `pm-triage`, branched validators in `pm-scoping`/`pm-incremental-update`) needs another pass once the V1 component is real. Treat the additional workflows as **layout regression tests** for V1, not as final designs.

## Files in this bundle

```
design_handoff_workflow/
├── README.md                       ← you are here
├── Tripwire - Workflow.html        ← the V1 prototype on a design canvas
├── Tripwire - Workflow Handoff.html ← the spec doc (anatomy, tokens, schema, behavior)
├── screenshots/
│   ├── canvas-overview.png         ← all variations on the canvas
│   ├── coding-session-full.png     ← V1 · coding-session, full chart
│   └── coding-session-detail.png   ← detail crop
├── workflow/                       ← V1 implementation (the part to recreate)
│   ├── data.jsx                    ← canonical workflow definitions (mirrors workflow.yaml)
│   ├── registry.jsx                ← validator/prompt-check/JIT/skill metadata
│   ├── atoms.jsx                   ← shared visual primitives (colors, stamps, glyphs)
│   ├── layout.jsx                  ← pure layout function (workflow → coords)
│   ├── flowchart.jsx               ← SVG renderer
│   ├── navigator.jsx               ← family-grouped tab rail (workflow switcher)
│   └── page.jsx                    ← page assembly: navigator + chart
├── philosophy/styles.css           ← design tokens (paper/ink/rule/type) — same as redesign handoff
└── screens/                        ← shell + canvas only (so the prototype renders standalone)
    ├── screen-shell.jsx
    ├── design-canvas.jsx
    ├── browser-window.jsx
    ├── theme.jsx
    ├── theme-tweaks.jsx
    ├── tweaks-panel.jsx
    └── scenario.jsx
```

Open `Tripwire - Workflow Handoff.html` for the visual spec — anatomy diagrams, element specs, data schema, behavior table. Open `Tripwire - Workflow.html` to see the live prototype.

## Tokens

This screen uses the **same tokens** as the broader Tripwire redesign — paper/ink/rule/gate/tripwire/info palette, Bricolage Grotesque + Instrument Serif + Geist Mono. See the existing `design_handoff_tripwire_redesign/README.md` for the canonical token list. **Do not redeclare colors or type here.**

The Workflow page introduces no new tokens. It does, however, use the existing palette in some new ways — most notably, `actor` colour stripes on the left edge of every transition node (PM ochre / Coding green / Code indigo). These are aliases of `tripwire`/`gate`/`info`, not new colours.

## Implementation notes

1. The chart is a single inline SVG. The data flow is: `workflow.yaml` → typed `Workflow` object → `layoutWorkflow(wf, opts)` → render. Keep the layout function pure and unit-testable; hover/click state is the renderer's concern.
2. The transition node is the workhorse atom. Get this right and the rest follows. See the spec doc for exact dimensions.
3. The lock-badge gate panel is a *progressive disclosure* of validator/prompt-check details. The badge says how many checks; clicking opens an inline panel with each check name + its blurb. The panel is anchored to the transition (positioned in the document, not in SVG).
4. Branched outcomes (e.g. `pm-session-review` → approve | request-changes) render as a diamond with two outgoing edges, each labelled. The layout function already handles this when `gateMode='diamond'` — V1 ships diamond mode.
5. JIT prompts are standalone nodes in the *proof shelf* (the band below the main line). They aren't on the routing path; they're "interventions that can fire while the agent works in this status." Anchor them to their `status`, not to a transition.
6. Artifacts are tiles at the bottom of each region (one tile per `artifacts.produces` entry). They are not connected by edges — proximity alone communicates the relationship. Resist adding connectors here; the chart is already dense.

## Open questions

- Live data: should the chart reflect the *current* state of in-flight sessions (e.g. highlight the executing region for sessions that are executing right now), or stay a pure definition view? The mock is definition-only.
- Validator/prompt-check rules: the gate panel currently lists names + a hand-written blurb. Should clicking a check deep-link to its source definition (Python validator, prompt-check entry)? Probably yes, but post-V1.
- Per-workflow density: should `pm-triage` (4 statuses, 4 routes) render at the same width as `coding-session` (6 statuses, 8 routes), or auto-fit?
- Drift overlay: the original brief mentioned drift (sessions deviating from the canonical workflow). The data layer (`DRIFT`) is plumbed but empty. Confirm whether drift overlays ship with V1 or fast-follow.
