// design_handoff_workflow/handoff/schema.jsx — data schema + registry
const HdSchema = () => (
  <HdSection id="schema" eyebrow="03 · Data schema"
             title="Three flat objects, one helper."
             sub={<>The chart is a pure function of these objects. Define them as TypeScript interfaces in the codebase; populate them server-side from <Mono>workflow.yaml</Mono>; ship the whole bundle to the client. No client-side derivation needed beyond the layout function.</>}>

    <div style={{display:'grid', gridTemplateColumns:'1fr', gap:32}}>
      <HdPanel title="Workflow" eyebrow="entity · 1 of 3" tone="rule">
        <p>The top-level object. One per workflow in <Mono>workflow.yaml</Mono>; six total.</p>
        <HdCode lang="typescript">{`type Workflow = {
  id: string;                    // 'coding-session', 'pm-scoping', ...
  family: 'coding' | 'pm' | 'maintenance';
  actor: 'pm-agent' | 'coding-agent' | 'code';   // primary actor; routes can override
  trigger: string;               // 'session.spawn', 'command.pm-scope', ...
  label: string;                 // human label ('coding-session')
  blurb: string;                 // italic-serif tagline ('one session: plan, execute, review, ship.')
  statuses: Status[];            // ordered: declaration order = west→east
  routes: Route[];               // unordered; the layout fn places them
};`}</HdCode>
      </HdPanel>

      <HdPanel title="Status" eyebrow="entity · 2 of 3" tone="info">
        <p>One per band. Order in the array determines left-to-right placement.</p>
        <HdCode lang="typescript">{`type Status = {
  id: string;                    // 'planned', 'queued', 'executing', ...
  blurb: string;                 // 1–3 word italic-serif descriptor under the title
  terminal?: boolean;            // last status; renders the filled circle marker
  artifacts?: {
    consumes?: { id: string; label: string }[];
    produces?: { id: string; label: string }[];   // becomes artifact tile(s) at region bottom
  };
};`}</HdCode>
      </HdPanel>

      <HdPanel title="Route" eyebrow="entity · 3 of 3" tone="gate">
        <p>One per transition. The layout function classifies routes into branched / non-branched and lane-allocates them.</p>
        <HdCode lang="typescript">{`type Route = {
  id: string;                    // unique within workflow ('queued-to-executing')
  actor: 'pm-agent' | 'coding-agent' | 'code';   // who acts on this transition
  command?: string | null;       // 'pm-session-spawn' — shows as ▷ prefix; null if none
  from: string;                  // status id, or 'source:<name>' for a west port
  to:   string;                  // status id, or 'sink:<name>'   for an east port
  kind: 'forward' | 'return' | 'side' | 'loop' | 'terminal';
  label: string;                 // sans label inside the transition box
  controls: {
    validators: string[];        // validator IDs ('v_workflow_well_formed', ...)
    prompt_checks: string[];     // prompt-check IDs ('pm-session-create')
    jit_prompts: string[];       // (deprecated on Route — JITs anchor to status)
  };
  skills: string[];              // ['project-manager', 'verification']
  emits?: {
    artifacts?: { id: string; label: string }[];
    events?:    string[];
    comments?:  string[];
  };
};`}</HdCode>
        <p style={{marginTop:14}}><strong>Branch metadata</strong> is kept separate. When two routes share a logical command (e.g. <Mono>pm-session-review</Mono> can approve or request changes), they appear in <Mono>BRANCHES</Mono>:</p>
        <HdCode lang="typescript">{`const BRANCHES: Record<RouteId, { branchOf: string; outcome: string }> = {
  'review-approved':         { branchOf: 'pm-session-review', outcome: 'approve' },
  'review-changes-requested':{ branchOf: 'pm-session-review', outcome: 'request changes' },
  // ...
};`}</HdCode>
        <p>The renderer checks <Mono>BRANCHES[route.id]</Mono>; when present, the layout collapses both outcomes onto a single diamond at the source region's east edge with two outgoing edges, each labelled with the outcome.</p>
      </HdPanel>

      <HdPanel title="Registry" eyebrow="lookup tables" tone="trip">
        <p>Three flat dictionaries that decorate the chart. Hand-written; stable; live in the codebase rather than in <Mono>workflow.yaml</Mono>.</p>
        <HdCode lang="typescript">{`// validator name → 1-line description
const VALIDATORS: Record<string, string> = {
  v_workflow_well_formed: 'workflow.yaml parses & is well-formed',
  v_uuid_present:         'all entities have UUIDs',
  // ...
};

// prompt-check name → 1-line description
const PROMPT_CHECKS: Record<string, string> = {
  'pm-session-create': 'PM creating session: scope/standards/handoff present?',
  // ...
};

// JIT prompt definition + where it anchors in the chart
type Jit = { id: string; workflow: string; status: string };
const JIT_ANCHORS: Jit[] = [
  { id: 'self-review',         workflow: 'coding-session', status: 'in_review' },
  { id: 'phase-transition',    workflow: 'coding-session', status: 'executing' },
  // ...
];

// when a (route, skill) load is conditional rather than mandatory
const CONDITIONAL_SKILLS: Record<\`\${string}|\${string}\`, string> = {
  'executing-to-review|backend-development': 'when scope touches backend',
  // ...
};`}</HdCode>
      </HdPanel>

      <HdPanel title="Helper" eyebrow="api" tone="ink">
        <p>One pure function that the renderer calls. Pure means: no DOM, no state, no fetch. Returns deterministic coordinates for a given workflow + options.</p>
        <HdCode lang="typescript">{`function layoutWorkflow(
  workflow: Workflow,
  options?: { width?: number; height?: number; gateMode?: 'lock' | 'diamond' }
): {
  width: number;
  height: number;
  regions:     LaidOutRegion[];
  transitions: LaidOutTransition[];   // includes branch diamonds when gateMode='diamond'
  edges:       LaidOutEdge[];          // each edge is a polyline + actor + kind
  jits:        LaidOutJit[];
  ports:       LaidOutPort[];
  mainY: number; northY: number; southY: number;
  proofTop: number; artifactRowY: number;
};`}</HdCode>
        <p style={{marginTop:14}}>The reference implementation is in <Mono>workflow/layout.jsx</Mono> — under 270 lines, no dependencies. Treat it as the spec for the production version: same signature, same field names, same lane Y-offsets.</p>
      </HdPanel>
    </div>
  </HdSection>
);

window.HdSchema = HdSchema;
