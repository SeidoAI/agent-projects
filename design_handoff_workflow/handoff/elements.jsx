// design_handoff_workflow/handoff/elements.jsx — atom-by-atom specs
const HdElements = () => (
  <HdSection id="elements" eyebrow="02 · Elements"
             title="Eight atoms, no more."
             sub={<>Every chart is composed from these primitives. Get the dimensions and tones in this section right, and every workflow renders.</>}>

    <ElementCard
      n="01" name="Region (status band)"
      blurb="One vertical band per status, drawn west→east in declaration order. Alternating cream tones to make the boundaries scannable."
      sample={<RegionSample/>}
      specs={[
        ['width',     <>uniform: <Mono>(chartWidth − 2·padX) / N</Mono>. With padX 60 and 1480 chart width, ≈ 226px per band for 6 statuses.</>],
        ['fills',     <>even index <Mono>#efebde</Mono>, odd index <Mono>#e8e2cf</Mono>. Border <Mono>#c9bfae</Mono> at 0.7px, 70% opacity.</>],
        ['header',    <>top 90px reserved. Mono ordinal (10px, tracked 0.18em, ink-3) on row 1; sans status name (Bricolage 22/600) on row 2; italic serif blurb (13/italic, ink-2) on row 3.</>],
        ['terminal',  <>terminal status gets a 6px filled ink circle at top-right of the header.</>],
        ['proof shelf', <>marked by a dashed horizontal rule near the bottom; mono caption <Mono>PROOF SHELF</Mono> below the rule.</>],
      ]}/>

    <ElementCard
      n="02" name="Transition node (rectangular)"
      blurb="The default route atom. A rectangle that sits on a Y-lane, owned by the acting agent. The left edge is a 4px coloured stripe; the agent label is mono uppercase in the bottom-right."
      sample={<TransitionSample/>}
      specs={[
        ['size',     <><Mono>168 × 50</Mono> (width × height). Always exact — never auto-fit.</>],
        ['fill / border', <>fill <Mono>#f0eee9</Mono>; border 1.6px in actor colour; corner radius 3.</>],
        ['left stripe', <>4px wide solid actor colour, full height; sits inside the border.</>],
        ['command line', <>mono 9.5px, ink-3, prefix <Mono>▷</Mono>, at <Mono>(left+12, top+14)</Mono>. Optional — skipped when route has no command.</>],
        ['label', <>Bricolage 13/600, letter-spacing −0.005em, ink. Below the command line if present, else vertically centred.</>],
        ['actor stamp', <>mono 8.5px, weight 600, tracked 0.06em, in actor colour, anchored bottom-right with 8px padding. Text matches <Mono>ACTOR_LABEL[actor].toUpperCase()</Mono>.</>],
        ['skill ribbon', <>mono 8.5px, ink-info colour, prefix <Mono>▸</Mono>, stacked above the box (one skill per line, max 3, hard-truncated at 14 chars). Conditional skills get a dotted underline + trailing <Mono>?</Mono>.</>],
      ]}/>

    <ElementCard
      n="03" name="Branch diamond"
      blurb="When a single command emits more than one outcome (e.g. pm-session-review → approve | request changes), the transition is rendered as a diamond at the source region's east edge. Each outcome edge gets a labelled chip."
      sample={<DiamondSample/>}
      specs={[
        ['size',    <>diamond is <Mono>120 × 64</Mono> (points: <Mono>0,−32 / 60,0 / 0,32 / −60,0</Mono>).</>],
        ['fill / border', <>fill <Mono>#f0eee9</Mono>; border 1.6px in actor colour.</>],
        ['command line', <>mono 9.5px, ink-3, prefix <Mono>▷</Mono>, centred at y −2.</>],
        ['label', <>Bricolage 12/600, ink, centred at y +14. Always reads <em>"decision"</em> — the differentiator is the outcomes, not the diamond label.</>],
        ['skills caption', <>mono 9px, ink-info, centred above the diamond at y −44; up to two skills, joined by <Mono> · </Mono>.</>],
        ['outcomes', <>each outgoing edge gets an outcome chip near its midpoint: 64×14 rect, mono 9px label, ink text, paper fill, 0.9px actor-colour border.</>],
        ['placement', <>diamond center sits at <Mono>fromR.x + fromR.w − 8</Mono> on the main Y. Outcome transition boxes (if rendered) are placed past the diamond on their assigned lane.</>],
      ]}/>

    <ElementCard
      n="04" name="Edge (route line)"
      blurb="A polyline from one anchor to another, curved into orthogonal segments with rounded corners. Stroke colour = actor; dash pattern = route kind."
      sample={<EdgeSample/>}
      specs={[
        ['stroke',     <>2px, actor colour. The arrowhead at the consumer end uses a 7×7 marker filled in the same colour.</>],
        ['forward',    <>solid line.</>],
        ['return',     <>dashed <Mono>7 5</Mono>.</>],
        ['side',       <>dashed <Mono>10 4 2 4</Mono>.</>],
        ['loop',       <>dashed <Mono>4 4</Mono>.</>],
        ['terminal',   <>solid; lands at a sink port (filled circle).</>],
        ['routing',    <>polyline goes from anchor → vertical drop to lane Y → horizontal across → vertical to next anchor. Corner radius 9–10 (Q-curve smoothing). Detour edges (returns, sides, loops) use a midpoint Y override.</>],
        ['outcome label', <>only on edges leaving a diamond — see Element 03.</>],
      ]}/>

    <ElementCard
      n="05" name="Gate badge"
      blurb="A small lock-glyph + counter, placed inside the transition node at the top-right corner. Indicates how many validators + prompt-checks gate this route. Click to expand."
      sample={<GateSample/>}
      specs={[
        ['size',    <>40 × 14 inset, anchored at <Mono>(box.right − 44, box.top + 4)</Mono>.</>],
        ['fill / border', <>fill <Mono>#faf8f3</Mono>; border 1px gate-green <Mono>#2d5a3d</Mono>.</>],
        ['glyph',   <>14×14 lock glyph (rectangle body + arched shackle), gate-green stroke 1px.</>],
        ['count',   <>mono 9/600, gate-green, prefix <Mono>×</Mono>. Sum of <Mono>controls.validators.length + controls.prompt_checks.length</Mono>.</>],
        ['empty case', <>do not render when count is 0. Don't show a "0" badge.</>],
        ['interaction', <>click toggles a panel anchored below the box (see Behaviours).</>],
      ]}/>

    <ElementCard
      n="06" name="JIT prompt node"
      blurb="A standalone ochre badge in the proof shelf. Anchored to a status, not a transition. These are interventions that can fire while the agent is working — write-count limits, cost ceilings, self-review reminders."
      sample={<JitSample/>}
      specs={[
        ['size',    <>26×26 rounded square, corner radius 6.</>],
        ['fill / border', <>fill <Mono>#f0eee9</Mono>; border 1.5px tripwire ochre <Mono>#b8741a</Mono>.</>],
        ['glyph',   <>mono <Mono>!</Mono> centred, 13/700, ochre.</>],
        ['label',   <>mono 8.5px, ink-2, centred 28px below the badge.</>],
        ['placement', <>stacked vertically at the region's centre column inside the proof shelf, starting at <Mono>proofTop + 26</Mono>, step <Mono>50</Mono>.</>],
      ]}/>

    <ElementCard
      n="07" name="Artifact tile"
      blurb="A small ticket-cut card at the very bottom of a region, listing what the routes inside this region produce. Proximity-only — never connected by an edge."
      sample={<ArtSample/>}
      specs={[
        ['shape',   <>116×30 rectangle with the top-right corner notched: <Mono>M 0 0 H 100 L 116 12 V 30 H 0 Z</Mono>.</>],
        ['fill / border', <>fill <Mono>#f0eee9</Mono>; border 0.9px ink-3, dashed <Mono>3 2</Mono>.</>],
        ['label',   <>mono 9.5px, ink-2, prefix <Mono>◫</Mono>, centred.</>],
        ['placement', <>region centre X; Y at <Mono>regionBottom − 36</Mono>. One tile per <Mono>artifacts.produces</Mono> entry; the V1 mock caps at one — extend to multiple if needed.</>],
      ]}/>

    <ElementCard
      n="08" name="Source / sink port"
      blurb="External anchors at the west (sources) and east (sinks) edges of the chart. A source is hollow + dotted; a sink is filled."
      sample={<PortSample/>}
      specs={[
        ['size',    <>9px radius circle.</>],
        ['source',  <>fill <Mono>#f0eee9</Mono>, border 1.6px ink, plus a 2.5px ink dot at centre.</>],
        ['sink',    <>fill ink (solid).</>],
        ['label',   <>mono 10px, ink-2, anchored beside the port (left for source, right for sink). Below it: mono 8px tracked 0.12em with the kind in uppercase.</>],
        ['x position', <>source at <Mono>padX − 28</Mono>; sink at <Mono>chartWidth − padX + 28</Mono>. Both on the main Y.</>],
      ]}/>
  </HdSection>
);

const ElementCard = ({n, name, blurb, sample, specs}) => (
  <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:36,
                marginTop:32, paddingTop:32, borderTop:`1px dashed ${HD_EDGE2}`}}>
    <div>
      <div style={{display:'flex', alignItems:'baseline', gap:12}}>
        <span style={{fontFamily:HD_F_MONO, fontSize:11, fontWeight:600,
                       letterSpacing:'0.18em', color:HD_INK3}}>{n}</span>
        <h3 style={{margin:0, fontFamily:HD_F_DISP, fontWeight:600, fontSize:24,
                     letterSpacing:'-0.015em'}}>{name}</h3>
      </div>
      <p style={{margin:'10px 0 18px', fontFamily:HD_F_SER, fontStyle:'italic',
                  fontSize:15, lineHeight:1.45, color:HD_INK2}}>{blurb}</p>
      <div style={{background:'#efebde', border:`1px solid ${HD_EDGE}`, padding:24,
                    minHeight:160, display:'flex', alignItems:'center',
                    justifyContent:'center'}}>
        {sample}
      </div>
    </div>
    <div>
      <HdEyebrow>spec</HdEyebrow>
      <div style={{marginTop:8}}>
        <HdSpecTable rows={specs}/>
      </div>
    </div>
  </div>
);

// ── samples ────────────────────────────────────────────────────────────
const RegionSample = () => (
  <svg viewBox="0 0 360 200" width="100%" style={{maxWidth:360, display:'block'}}>
    <rect x="0" y="0" width="180" height="200" fill="#efebde"
          stroke={HD_EDGE} strokeWidth="0.7"/>
    <rect x="180" y="0" width="180" height="200" fill="#e8e2cf"
          stroke={HD_EDGE} strokeWidth="0.7"/>
    <line x1="180" y1="0" x2="180" y2="200" stroke={HD_EDGE} strokeOpacity="0.6"/>
    <text x="12" y="20" fontFamily={HD_F_MONO} fontSize="9.5"
          fill={HD_INK3} letterSpacing="0.18em">03 · STATUS</text>
    <text x="12" y="46" fontFamily={HD_F_DISP} fontWeight="600" fontSize="22"
          fill={HD_INK} letterSpacing="-0.015em">executing</text>
    <text x="12" y="66" fontFamily={HD_F_SER} fontStyle="italic" fontSize="13"
          fill={HD_INK2}>agent working</text>
    <line x1="8" y1="78" x2="172" y2="78" stroke={HD_EDGE} strokeOpacity="0.5"/>
    <text x="192" y="20" fontFamily={HD_F_MONO} fontSize="9.5"
          fill={HD_INK3} letterSpacing="0.18em">04 · STATUS</text>
    <text x="192" y="46" fontFamily={HD_F_DISP} fontWeight="600" fontSize="22"
          fill={HD_INK} letterSpacing="-0.015em">in_review</text>
    <text x="192" y="66" fontFamily={HD_F_SER} fontStyle="italic" fontSize="13"
          fill={HD_INK2}>pm reviewing</text>
    <line x1="188" y1="78" x2="352" y2="78" stroke={HD_EDGE} strokeOpacity="0.5"/>
    <line x1="8" y1="156" x2="172" y2="156" stroke={HD_EDGE} strokeOpacity="0.5" strokeDasharray="3 4"/>
    <line x1="188" y1="156" x2="352" y2="156" stroke={HD_EDGE} strokeOpacity="0.5" strokeDasharray="3 4"/>
    <text x="12" y="172" fontFamily={HD_F_MONO} fontSize="8.5"
          fill={HD_INK3} letterSpacing="0.18em">PROOF SHELF</text>
    <text x="192" y="172" fontFamily={HD_F_MONO} fontSize="8.5"
          fill={HD_INK3} letterSpacing="0.18em">PROOF SHELF</text>
  </svg>
);

const TransitionSample = () => (
  <svg viewBox="0 0 280 130" width="100%" style={{maxWidth:280}}>
    <g transform="translate(140 70)">
      <text x="-80" y="-44" fontFamily={HD_F_MONO} fontSize="8.5" fill={HD_INFO}>▸ project-manager</text>
      <text x="-80" y="-32" fontFamily={HD_F_MONO} fontSize="8.5" fill={HD_INFO}>▸ backend-develop…</text>
      <rect x="-84" y="-25" width="168" height="50" fill={HD_PAPER}
            stroke={HD_TRIP} strokeWidth="1.6" rx="3"/>
      <rect x="-84" y="-25" width="4" height="50" fill={HD_TRIP}/>
      <text x="-72" y="-11" fontFamily={HD_F_MONO} fontSize="9.5"
            fill={HD_INK3} letterSpacing="0.04em">▷ pm-session-spawn</text>
      <text x="-72" y="5" fontFamily={HD_F_DISP} fontWeight="600"
            fontSize="13" fill={HD_INK}>spawn coding agent</text>
      <text x="76" y="17" textAnchor="end" fontFamily={HD_F_MONO}
            fontSize="8.5" fontWeight="600" fill={HD_TRIP}
            letterSpacing="0.06em">PM</text>
      {/* gate badge */}
      <g transform="translate(36 -21)">
        <rect x="0" y="0" width="40" height="14" fill={HD_PAPER2}
              stroke={HD_GATE} strokeWidth="1"/>
        <path d="M 4 9 V 7 a2 2 0 0 1 4 0 V 9" stroke={HD_GATE}
              strokeWidth="1" fill="none"/>
        <rect x="3" y="9" width="6" height="4" stroke={HD_GATE}
              strokeWidth="1" fill="none"/>
        <text x="14" y="10" fontFamily={HD_F_MONO} fontSize="9"
              fontWeight="600" fill={HD_GATE} letterSpacing="0.04em">×14</text>
      </g>
    </g>
  </svg>
);

const DiamondSample = () => (
  <svg viewBox="0 0 320 200" width="100%" style={{maxWidth:320}}>
    <g transform="translate(160 100)">
      <text x="0" y="-44" textAnchor="middle" fontFamily={HD_F_MONO}
            fontSize="9" fill={HD_INFO}>▸ project-manager · verification</text>
      <polygon points="0,-32 60,0 0,32 -60,0" fill={HD_PAPER}
               stroke={HD_TRIP} strokeWidth="1.6"/>
      <text x="0" y="-2" textAnchor="middle" fontFamily={HD_F_MONO}
            fontSize="9.5" fill={HD_INK3}>▷ pm-session-review</text>
      <text x="0" y="14" textAnchor="middle" fontFamily={HD_F_DISP}
            fontWeight="600" fontSize="12" fill={HD_INK}>decision</text>
      {/* outcome chips */}
      <g transform="translate(96 -18)">
        <rect x="-32" y="-9" width="64" height="14" fill={HD_PAPER}
              stroke={HD_TRIP} strokeWidth="0.9"/>
        <text x="0" y="2" textAnchor="middle" fontFamily={HD_F_MONO}
              fontSize="9" fill={HD_INK} letterSpacing="0.04em">approve</text>
      </g>
      <g transform="translate(96 18)">
        <rect x="-40" y="-9" width="80" height="14" fill={HD_PAPER}
              stroke={HD_TRIP} strokeWidth="0.9"/>
        <text x="0" y="2" textAnchor="middle" fontFamily={HD_F_MONO}
              fontSize="9" fill={HD_INK} letterSpacing="0.04em">request changes</text>
      </g>
      <line x1="60" y1="0" x2="64" y2="-18" stroke={HD_TRIP} strokeWidth="2"/>
      <line x1="60" y1="0" x2="64" y2="18" stroke={HD_TRIP} strokeWidth="2" strokeDasharray="6 4"/>
    </g>
  </svg>
);

const EdgeSample = () => (
  <svg viewBox="0 0 360 200" width="100%" style={{maxWidth:360}}>
    <defs>
      <marker id="es-arr" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 Z" fill={HD_INK}/>
      </marker>
    </defs>
    {[
      ['forward', null, 30],
      ['return',  '7 5', 70],
      ['side',    '10 4 2 4', 110],
      ['loop',    '4 4', 150],
    ].map(([k, dash, y]) => (
      <g key={k}>
        <text x="20" y={y+4} fontFamily={HD_F_MONO} fontSize="10"
              fill={HD_INK2} letterSpacing="0.06em">{k}</text>
        <path d={`M 100 ${y} L 320 ${y}`}
              stroke={HD_INK} strokeWidth="2" fill="none"
              strokeDasharray={dash || null}
              markerEnd="url(#es-arr)"/>
      </g>
    ))}
  </svg>
);

const GateSample = () => (
  <svg viewBox="0 0 240 120" width="100%" style={{maxWidth:240}}>
    <g transform="translate(120 60)">
      <rect x="-84" y="-25" width="168" height="50" fill={HD_PAPER}
            stroke={HD_TRIP} strokeWidth="1.6" rx="3"/>
      <rect x="-84" y="-25" width="4" height="50" fill={HD_TRIP}/>
      <text x="-72" y="3" fontFamily={HD_F_DISP} fontWeight="600"
            fontSize="12" fill={HD_INK}>queue session</text>
      <g transform="translate(36 -21)">
        <rect x="0" y="0" width="40" height="14" fill={HD_PAPER2}
              stroke={HD_GATE} strokeWidth="1"/>
        <path d="M 4 9 V 7 a2 2 0 0 1 4 0 V 9" stroke={HD_GATE}
              strokeWidth="1" fill="none"/>
        <rect x="3" y="9" width="6" height="4" stroke={HD_GATE}
              strokeWidth="1" fill="none"/>
        <text x="14" y="10" fontFamily={HD_F_MONO} fontSize="9"
              fontWeight="600" fill={HD_GATE} letterSpacing="0.04em">×6</text>
      </g>
    </g>
  </svg>
);

const JitSample = () => (
  <svg viewBox="0 0 200 160" width="100%" style={{maxWidth:200}}>
    {[
      [60, 50, 'self-review'],
      [60, 110, 'cost-ceiling'],
    ].map(([x, y, lbl]) => (
      <g key={lbl} transform={`translate(${x} ${y})`}>
        <rect x="-13" y="-13" width="26" height="26" rx="6"
              fill={HD_PAPER} stroke={HD_TRIP} strokeWidth="1.5"/>
        <text x="0" y="4" textAnchor="middle" fontFamily={HD_F_MONO}
              fontSize="13" fontWeight="700" fill={HD_TRIP}>!</text>
        <text x="0" y="28" textAnchor="middle" fontFamily={HD_F_MONO}
              fontSize="8.5" fill={HD_INK2}>{lbl}</text>
      </g>
    ))}
  </svg>
);

const ArtSample = () => (
  <svg viewBox="0 0 280 120" width="100%" style={{maxWidth:280}}>
    {[
      [70, 'plan.md'],
      [200, 'review notes'],
    ].map(([x, lbl]) => (
      <g key={lbl} transform={`translate(${x} 50)`}>
        <g transform="translate(-58, 0)">
          <path d="M 0 0 H 100 L 116 12 V 30 H 0 Z" fill={HD_PAPER}
                stroke={HD_INK3} strokeDasharray="3 2" strokeWidth="0.9"/>
          <path d="M 100 0 V 12 H 116" fill="none" stroke={HD_INK3}
                strokeWidth="0.9" strokeDasharray="3 2"/>
          <text x="58" y="20" textAnchor="middle" fontFamily={HD_F_MONO}
                fontSize="9.5" fill={HD_INK2}>◫ {lbl}</text>
        </g>
      </g>
    ))}
  </svg>
);

const PortSample = () => (
  <svg viewBox="0 0 280 120" width="100%" style={{maxWidth:280}}>
    {/* source */}
    <g transform="translate(60 60)">
      <circle r="9" fill={HD_PAPER} stroke={HD_INK} strokeWidth="1.6"/>
      <circle r="2.5" fill={HD_INK}/>
      <text x="-14" y="3" textAnchor="end" fontFamily={HD_F_MONO}
            fontSize="10" fill={HD_INK2}>issue</text>
      <text x="-14" y="16" textAnchor="end" fontFamily={HD_F_MONO}
            fontSize="8" fill={HD_INK3} letterSpacing="0.12em">SOURCE</text>
    </g>
    {/* sink */}
    <g transform="translate(220 60)">
      <circle r="9" fill={HD_INK}/>
      <text x="14" y="3" fontFamily={HD_F_MONO} fontSize="10" fill={HD_INK2}>main</text>
      <text x="14" y="16" fontFamily={HD_F_MONO} fontSize="8"
            fill={HD_INK3} letterSpacing="0.12em">SINK</text>
    </g>
  </svg>
);

window.HdElements = HdElements;
