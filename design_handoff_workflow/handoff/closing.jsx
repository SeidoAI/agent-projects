// design_handoff_workflow/handoff/closing.jsx — implementation order, file map, screenshots
const HdClosing = () => (
  <>
    <HdSection id="implementation" eyebrow="06 · Implementation order"
               title="Smallest atom, then up."
               sub={<>Build the chart bottom-up. Get the layout function and the transition node right; the rest composes.</>}>
      <ol style={{margin:'8px 0 0', paddingLeft:24, fontFamily:HD_F_TEXT, fontSize:15,
                   lineHeight:1.7, color:HD_INK, maxWidth:780}}>
        <li><strong>Types &amp; data fixture.</strong> Land <Mono>Workflow / Status / Route</Mono> as TS interfaces. Populate with the six-workflow fixture from <Mono>workflow/data.jsx</Mono>; verify it round-trips against the real <Mono>workflow.yaml</Mono>.</li>
        <li><strong>Registry.</strong> <Mono>VALIDATORS</Mono>, <Mono>PROMPT_CHECKS</Mono>, <Mono>JIT_ANCHORS</Mono>, <Mono>CONDITIONAL_SKILLS</Mono>, <Mono>BRANCHES</Mono>. Hand-typed; lives next to the chart component.</li>
        <li><strong><Mono>layoutWorkflow()</Mono>.</strong> Port from the reference. Pure function, no React. Unit-test the lane-allocation rules with a couple of fixtures.</li>
        <li><strong>Transition node.</strong> The hardest atom. Get the actor stripe, the command-line, the label, the actor stamp, and the skill ribbon stacked correctly. Work alone in Storybook before placing in a chart.</li>
        <li><strong>Edges.</strong> Polyline rendering with rounded corners. Same code path for forward / return / side / loop — only the dash and lane Y differ.</li>
        <li><strong>Branch diamond.</strong> Compose with <Mono>BRANCHES</Mono>. Outcome chips on the outgoing edges.</li>
        <li><strong>Gate badge + panel.</strong> Badge is SVG; panel is a positioned <Mono>&lt;div&gt;</Mono> outside the SVG. Use a portal if the parent constrains overflow.</li>
        <li><strong>JIT nodes &amp; artifact tiles.</strong> Trivial once anchors are in place.</li>
        <li><strong>Page chrome.</strong> Family navigator, header, inline legend. Re-uses existing tokens and atoms.</li>
        <li><strong>Workflow switching.</strong> URL-driven (<Mono>?wf=coding-session</Mono>) so deep links work and browser-back behaves.</li>
      </ol>
    </HdSection>

    <HdSection id="screenshots" eyebrow="07 · Reference"
               title="The V1 chart, captured."
               sub={<>The final mock for the canonical workflow. Every spec in this document is keyed to what's drawn here.</>}>
      <div style={{marginTop:24}}>
        <ScreenshotFigure n="01" cap="Coding-session workflow — full chart, the V1 reference render."
                          src="screenshots/coding-session-full.png"/>
        <ScreenshotFigure n="02" cap="Detail crop — note the skill ribbon stack on the spawn-coding-agent transition and the diamond between in_review and verified."
                          src="screenshots/coding-session-detail.png"/>
        <ScreenshotFigure n="03" cap="The design canvas with all directions — V1 (territory bands) is the chosen direction."
                          src="screenshots/canvas-overview.png"/>
      </div>
    </HdSection>

    <HdSection id="files" eyebrow="08 · File map"
               title="What's in the bundle."
               sub={<>The JSX files in this bundle are reference implementations — pure functions and React components that mirror the production architecture without the production toolchain. Lift the structure; rewrite through the codebase's stack.</>}>
      <HdCode lang="layout">{`design_handoff_workflow/
├── README.md                          ← project notes & open questions
├── Tripwire - Workflow.html           ← live prototype on a design canvas
├── Tripwire - Workflow Handoff.html   ← this document
│
├── workflow/                          ← THE PART TO RECREATE
│   ├── data.jsx                       ← canonical workflow definitions (mirrors workflow.yaml)
│   ├── registry.jsx                   ← VALIDATORS / PROMPT_CHECKS / JIT_ANCHORS / BRANCHES
│   ├── atoms.jsx                      ← shared visual primitives (colors, stamps, glyphs)
│   ├── layout.jsx                     ← pure layoutWorkflow() function — the spec
│   ├── flowchart.jsx                  ← SVG renderer — the spec
│   ├── navigator.jsx                  ← family-grouped tab rail
│   └── page.jsx                       ← page assembly
│
├── handoff/                           ← jsx for THIS spec doc — not for production
│   ├── styles.jsx                     ← local atoms (HdSection, HdPanel, HdSpecTable, ...)
│   ├── cover.jsx
│   ├── anatomy.jsx
│   ├── elements.jsx
│   ├── schema.jsx
│   ├── page-chrome.jsx
│   ├── behaviour.jsx
│   └── closing.jsx
│
├── screenshots/                       ← reference renders for §07
│   ├── coding-session-full.png
│   ├── coding-session-detail.png
│   └── canvas-overview.png
│
├── philosophy/styles.css              ← canonical tokens (DO NOT redeclare)
└── screens/                           ← shell + design-canvas (so the prototype renders)
`}</HdCode>

      <p style={{marginTop:24, fontFamily:HD_F_TEXT, fontSize:14.5, lineHeight:1.55,
                  color:HD_INK, maxWidth:760}}>
        <strong>Two files are the spec:</strong> <Mono>workflow/layout.jsx</Mono> and{' '}
        <Mono>workflow/flowchart.jsx</Mono>. Read them alongside this document. Everything
        in <Mono>handoff/</Mono> is supporting prose; everything in <Mono>screens/</Mono>{' '}
        is canvas chrome that does not ship.
      </p>
    </HdSection>

    <HdSection id="end" eyebrow="00 · end"
               title="Last words."
               sub={null}>
      <div style={{display:'flex', gap:32, marginTop:8, alignItems:'flex-end',
                    paddingBottom:120, borderBottom:`2px solid ${HD_INK}`}}>
        <p style={{margin:0, maxWidth:580, fontFamily:HD_F_SER, fontStyle:'italic',
                    fontSize:20, lineHeight:1.45, color:HD_INK2}}>
          The chart is dense because the framework is dense. The discipline is to
          render that density legibly — eight atoms, one lane allocation, no decorative
          lines. If a new affordance creeps in, ask whether it earns its place against
          the existing eight. The answer is usually no.
        </p>
        <div style={{flex:1}}/>
        <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end',
                      gap:6, fontFamily:HD_F_MONO, fontSize:11, color:HD_INK3,
                      letterSpacing:'0.06em'}}>
          <HdStamp tone="rule">approved</HdStamp>
          <span>handoff · v1 · territory</span>
          <span>workflow.yaml · v0.9.6</span>
        </div>
      </div>
    </HdSection>
  </>
);

const ScreenshotFigure = ({n, cap, src}) => (
  <figure style={{margin:'0 0 36px', padding:0}}>
    <div style={{background:'#efebde', border:`1px solid ${HD_EDGE}`,
                  padding:'10px 10px 14px'}}>
      <div style={{display:'flex', justifyContent:'space-between',
                    fontFamily:HD_F_MONO, fontSize:10, letterSpacing:'0.18em',
                    color:HD_INK3, marginBottom:8}}>
        <span>fig {n} · screenshot</span>
        <span>v1 · territory map</span>
      </div>
      <img src={src} alt={cap}
           style={{width:'100%', display:'block', border:`1px solid ${HD_EDGE}`,
                    background:HD_PAPER}}/>
    </div>
    <figcaption style={{marginTop:10, fontFamily:HD_F_SER, fontStyle:'italic',
                          fontSize:14, color:HD_INK2, lineHeight:1.45,
                          maxWidth:760}}>{cap}</figcaption>
  </figure>
);

window.HdClosing = HdClosing;
