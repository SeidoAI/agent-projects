// design_handoff_workflow/handoff/anatomy.jsx — page anatomy + spatial vocabulary
const HdAnatomy = () => (
  <HdSection id="anatomy" eyebrow="01 · Page anatomy"
             title="Territory underneath, routes over."
             sub={<>The chart reads west→east as a session moves through its lifecycle. Statuses are <em>territory</em>, drawn as alternating cream bands. Transitions are <em>routes</em>, drawn as colour-keyed boxes that sit on lanes above and below the boundary. Everything else hangs off this skeleton.</>}>
    <AnatomyDiagram/>

    <div style={{marginTop:48, display:'grid', gridTemplateColumns:'1fr 1fr', gap:24}}>
      <HdPanel title="The four directions" eyebrow="compass">
        <p style={{margin:'0 0 8px'}}>The chart's compass is annotated explicitly in the rendered SVG (see top + bottom rails). Each direction holds a different concern:</p>
        <table style={{width:'100%', borderCollapse:'collapse', marginTop:6}}>
          <tbody>
            {[
              ['WEST',  'INTENT',  'sources, the issue brief — what triggered this session'],
              ['NORTH', 'CONTROL', 'gates, validators, prompt-checks — the framework\'s rules'],
              ['EAST',  'CLOSURE', 'sinks, terminal states — where the session ends up'],
              ['SOUTH', 'PROOF',   'JIT prompts and artifacts — what the session produced'],
            ].map(([d, w, b]) => (
              <tr key={d} style={{borderTop:`1px dashed ${HD_EDGE}`}}>
                <td style={{padding:'6px 8px 6px 0', fontFamily:HD_F_MONO, fontSize:10,
                              letterSpacing:'0.18em', color:HD_INK3, width:60}}>{d}</td>
                <td style={{padding:'6px 12px 6px 0', fontFamily:HD_F_MONO, fontSize:10,
                              fontWeight:600, color:HD_INK, width:80}}>{w}</td>
                <td style={{padding:'6px 0', fontFamily:HD_F_SER, fontStyle:'italic',
                              fontSize:13, color:HD_INK2}}>{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </HdPanel>

      <HdPanel title="The three horizontal lanes" eyebrow="layout">
        <p style={{margin:'0 0 8px'}}>Inside each region (status band), routes are placed on one of three Y-lanes by their <Mono>kind</Mono>:</p>
        <ul style={{margin:'8px 0 0', paddingLeft:18, lineHeight:1.6}}>
          <li><Mono>kind: 'forward'</Mono> sits on the <strong>main line</strong> (default route — promote the session).</li>
          <li><Mono>kind: 'side'</Mono> rides the <strong>north lane</strong>, ~75px above main (alternate forward).</li>
          <li><Mono>kind: 'return'</Mono> rides the <strong>south lane</strong>, ~80px below main (loop back to a prior status).</li>
        </ul>
        <p style={{marginTop:8}}>Below the south lane lives the <strong>proof shelf</strong> — a horizontal band reserved for JIT prompts and artifact tiles. JITs are stacked vertically inside their owning region; artifacts sit at the very bottom edge.</p>
      </HdPanel>
    </div>
  </HdSection>
);

// SVG anatomy: a small annotated chart with callouts.
const AnatomyDiagram = () => {
  const W = 980, H = 540;
  const padX = 40, padY = 60;
  const N = 5;
  const regW = (W - padX*2) / N;
  const regY = padY + 30, regH = H - padY*2 - 30;
  const mainY = regY + 130;
  const northY = mainY - 70;
  const southY = mainY + 65;
  const proofY = mainY + 110;
  const STATUSES = ['planned', 'queued', 'executing', 'in_review', 'completed'];

  return (
    <div style={{background:'#efebde', border:`1px solid ${HD_EDGE}`, padding:'24px',
                  position:'relative'}}>
      <div style={{display:'flex', justifyContent:'space-between', marginBottom:14}}>
        <HdEyebrow>fig 01 · anatomy of the chart</HdEyebrow>
        <HdEyebrow>annotated</HdEyebrow>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:'block'}}>
        <defs>
          <marker id="hd-anat-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 Z" fill={HD_INK}/>
          </marker>
          <marker id="hd-anat-arrow-trip" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 Z" fill={HD_TRIP}/>
          </marker>
        </defs>

        {/* compass labels */}
        <g fontFamily={HD_F_MONO} fontSize="9" fill={HD_INK3} letterSpacing="0.18em">
          <text x={padX} y={padY-4}>WEST · INTENT</text>
          <text x={W/2} y={padY-4} textAnchor="middle">NORTH · CONTROL</text>
          <text x={W-padX} y={padY-4} textAnchor="end">EAST · CLOSURE</text>
          <text x={W/2} y={H-30} textAnchor="middle">SOUTH · PROOF</text>
        </g>

        {/* regions */}
        {STATUSES.map((s, i) => (
          <g key={s}>
            <rect x={padX + i*regW} y={regY} width={regW} height={regH}
                  fill={i%2===0 ? '#efebde' : '#e2dcc6'}
                  stroke={HD_EDGE} strokeWidth="0.7" strokeOpacity="0.7"/>
            <text x={padX + i*regW + 8} y={regY + 14}
                  fontFamily={HD_F_MONO} fontSize="8.5" fill={HD_INK3}
                  letterSpacing="0.18em">{String(i+1).padStart(2,'0')} · STATUS</text>
            <text x={padX + i*regW + 8} y={regY + 36}
                  fontFamily={HD_F_DISP} fontWeight="600" fontSize="16"
                  letterSpacing="-0.01em" fill={HD_INK}>{s}</text>
            {/* divider between header and lane area */}
            <line x1={padX + i*regW + 6} y1={regY + 50}
                  x2={padX + (i+1)*regW - 6} y2={regY + 50}
                  stroke={HD_EDGE} strokeOpacity="0.5"/>
            {/* divider for proof shelf */}
            <line x1={padX + i*regW + 6} y1={proofY - 10}
                  x2={padX + (i+1)*regW - 6} y2={proofY - 10}
                  stroke={HD_EDGE} strokeOpacity="0.5" strokeDasharray="3 4"/>
          </g>
        ))}
        {/* region dividers */}
        {STATUSES.slice(1).map((_, i) => (
          <line key={`bd-${i}`} x1={padX + (i+1)*regW} y1={regY}
                x2={padX + (i+1)*regW} y2={regY+regH}
                stroke={HD_EDGE} strokeOpacity="0.6"/>
        ))}

        {/* main line guide */}
        <line x1={padX} y1={mainY} x2={W-padX} y2={mainY}
              stroke={HD_EDGE} strokeOpacity="0.45" strokeDasharray="2 6"/>

        {/* sample transitions */}
        {/* forward 1 */}
        <SampleTx x={padX + regW} y={mainY} label="queue session" actor="pm" cmd="pm-session-queue"/>
        {/* forward 2 */}
        <SampleTx x={padX + regW*2} y={mainY} label="spawn agent" actor="pm" cmd="pm-session-spawn"/>
        {/* forward 3 */}
        <SampleTx x={padX + regW*3} y={mainY} label="submit for review" actor="coding"/>
        {/* diamond at boundary 4|5 */}
        <SampleDiamond x={padX + regW*4 - 8} y={mainY} cmd="pm-session-review"/>
        {/* return outcome */}
        <path d={`M ${padX + regW*4 - 8 + 50} ${mainY} L ${padX + regW*4} ${mainY}
                  L ${padX + regW*4} ${southY}
                  L ${padX + regW*3} ${southY}
                  L ${padX + regW*3} ${mainY}`}
              stroke={HD_INK} strokeWidth="1.6" fill="none" strokeDasharray="6 4"
              markerEnd="url(#hd-anat-arrow)"/>
        {/* main connectors */}
        <line x1={padX} y1={mainY} x2={padX + regW - 65} y2={mainY}
              stroke={HD_INK} strokeWidth="1.6" markerEnd="url(#hd-anat-arrow)"/>
        <line x1={padX + regW + 65} y1={mainY} x2={padX + regW*2 - 65} y2={mainY}
              stroke={HD_INK} strokeWidth="1.6" markerEnd="url(#hd-anat-arrow)"/>
        <line x1={padX + regW*2 + 65} y1={mainY} x2={padX + regW*3 - 65} y2={mainY}
              stroke={HD_INK} strokeWidth="1.6" markerEnd="url(#hd-anat-arrow)"/>
        <line x1={padX + regW*3 + 65} y1={mainY} x2={padX + regW*4 - 8 - 50} y2={mainY}
              stroke={HD_INK} strokeWidth="1.6" markerEnd="url(#hd-anat-arrow)"/>
        <line x1={padX + regW*4 + 50} y1={mainY} x2={padX + regW*4 + regW/2 - 4} y2={mainY}
              stroke={HD_INK} strokeWidth="1.6" markerEnd="url(#hd-anat-arrow)"/>

        {/* west port */}
        <circle cx={padX-14} cy={mainY} r="6" fill={HD_PAPER} stroke={HD_INK} strokeWidth="1.6"/>
        <circle cx={padX-14} cy={mainY} r="2" fill={HD_INK}/>
        <text x={padX-22} y={mainY+3} textAnchor="end"
              fontFamily={HD_F_MONO} fontSize="9" fill={HD_INK2}>issue</text>

        {/* east port (terminal) */}
        <circle cx={W-padX+14} cy={mainY} r="6" fill={HD_INK}/>
        <text x={W-padX+22} y={mainY+3}
              fontFamily={HD_F_MONO} fontSize="9" fill={HD_INK2}>main</text>

        {/* JIT prompts in proof shelf of region 3 (executing) */}
        {[0,1,2].map(k => (
          <g key={`jit-${k}`} transform={`translate(${padX + regW*2 + regW/2} ${proofY + 18 + k*40})`}>
            <rect x="-10" y="-10" width="20" height="20" rx="5"
                  fill={HD_PAPER} stroke={HD_TRIP} strokeWidth="1.4"/>
            <text x="0" y="3" textAnchor="middle" fontFamily={HD_F_MONO}
                  fontSize="11" fontWeight="700" fill={HD_TRIP}>!</text>
            <text x="14" y="3" fontFamily={HD_F_MONO} fontSize="8" fill={HD_INK2}>
              {['phase-transition','write-count','cost-ceiling'][k]}
            </text>
          </g>
        ))}
        {/* JIT prompt in region 4 */}
        <g transform={`translate(${padX + regW*3 + regW/2} ${proofY + 18})`}>
          <rect x="-10" y="-10" width="20" height="20" rx="5"
                fill={HD_PAPER} stroke={HD_TRIP} strokeWidth="1.4"/>
          <text x="0" y="3" textAnchor="middle" fontFamily={HD_F_MONO}
                fontSize="11" fontWeight="700" fill={HD_TRIP}>!</text>
          <text x="14" y="3" fontFamily={HD_F_MONO} fontSize="8" fill={HD_INK2}>self-review</text>
        </g>

        {/* artifact tile in region 2 (queued) */}
        <ArtTile x={padX + regW + regW/2} y={H - padY + 8} label="plan.md"/>
        <ArtTile x={padX + regW*2 + regW/2} y={H - padY + 8} label="implementation diff"/>
        <ArtTile x={padX + regW*3 + regW/2} y={H - padY + 8} label="review notes"/>

        {/* CALLOUTS */}
        {/* 1: region */}
        <Callout x1={padX + regW*0.5} y1={regY+20}
                 x2={padX - 4} y2={padY + 30 - 28}
                 label="01" />
        {/* 2: transition */}
        <Callout x1={padX + regW*1} y1={mainY - 16}
                 x2={padX + regW*0.55} y2={mainY - 60}
                 label="02" />
        {/* 3: branch diamond */}
        <Callout x1={padX + regW*4 - 8} y1={mainY - 32}
                 x2={padX + regW*4 + 30} y2={mainY - 70}
                 label="03" />
        {/* 4: return route */}
        <Callout x1={padX + regW*3.5} y1={southY}
                 x2={padX + regW*3.5} y2={southY + 30}
                 label="04" />
        {/* 5: JIT */}
        <Callout x1={padX + regW*2 + regW/2 + 12} y1={proofY + 56}
                 x2={padX + regW*2 + regW/2 + 70} y2={proofY + 60}
                 label="05" />
        {/* 6: artifact */}
        <Callout x1={padX + regW*2 + regW/2} y1={H - padY - 4}
                 x2={padX + regW*2 + regW/2 - 60} y2={H - padY + 40}
                 label="06" />
      </svg>
      <div style={{marginTop:14, display:'grid', gridTemplateColumns:'repeat(3, 1fr)',
                    gap:14, fontFamily:HD_F_TEXT, fontSize:13, color:HD_INK}}>
        <CalloutNote n="01" t="region" b="one band per status; alternating cream tones; status header (mono ordinal + sans label + serif blurb) at top." />
        <CalloutNote n="02" t="transition node" b="rectangular box on the boundary between two regions; left edge stripe + right-justified label coloured by acting agent." />
        <CalloutNote n="03" t="branch diamond" b="when one command can produce multiple outcomes (approve / request-changes), the transition becomes a diamond at the source region's east edge." />
        <CalloutNote n="04" t="return route" b="dashed; rides the south lane; sources from the diamond's bottom outcome and lands back on the prior region's main line." />
        <CalloutNote n="05" t="jit prompt" b="standalone ochre node in the proof shelf — an intervention that can fire while the agent is in this status; not on the routing path." />
        <CalloutNote n="06" t="artifact tile" b="ticket-cut card at the very bottom of the producing region; proximity-only — no edge to the producer." />
      </div>
    </div>
  );
};

const SampleTx = ({x, y, label, actor, cmd}) => {
  const c = actor === 'pm' ? HD_TRIP : actor === 'coding' ? HD_GATE : HD_INFO;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="-65" y="-22" width="130" height="42" fill={HD_PAPER}
            stroke={c} strokeWidth="1.5" rx="2"/>
      <rect x="-65" y="-22" width="3" height="42" fill={c}/>
      {cmd && (
        <text x="-58" y="-9" fontFamily={HD_F_MONO} fontSize="8"
              fill={HD_INK3} letterSpacing="0.04em">▷ {cmd}</text>
      )}
      <text x="-58" y={cmd ? 6 : -2}
            fontFamily={HD_F_DISP} fontWeight="600" fontSize="11.5"
            letterSpacing="-0.005em" fill={HD_INK}>{label}</text>
      <text x="60" y="14" textAnchor="end" fontFamily={HD_F_MONO}
            fontSize="7.5" fontWeight="600" fill={c}
            letterSpacing="0.06em">{actor.toUpperCase()}</text>
    </g>
  );
};

const SampleDiamond = ({x, y, cmd}) => (
  <g transform={`translate(${x} ${y})`}>
    <polygon points={`0,-26 50,0 0,26 -50,0`} fill={HD_PAPER}
             stroke={HD_TRIP} strokeWidth="1.6"/>
    <text x="0" y="-3" textAnchor="middle" fontFamily={HD_F_MONO}
          fontSize="8" fill={HD_INK3}>▷ {cmd}</text>
    <text x="0" y="11" textAnchor="middle" fontFamily={HD_F_DISP}
          fontWeight="600" fontSize="11" fill={HD_INK}>decision</text>
  </g>
);

const ArtTile = ({x, y, label}) => (
  <g transform={`translate(${x} ${y})`}>
    <g transform="translate(-50, 0)">
      <path d="M 0 0 H 84 L 100 12 V 26 H 0 Z" fill={HD_PAPER}
            stroke={HD_INK3} strokeWidth="0.9" strokeDasharray="3 2"/>
      <path d="M 84 0 V 12 H 100" fill="none" stroke={HD_INK3}
            strokeWidth="0.9" strokeDasharray="3 2"/>
      <text x="50" y="17" textAnchor="middle" fontFamily={HD_F_MONO}
            fontSize="9" fill={HD_INK2}>◫ {label}</text>
    </g>
  </g>
);

const Callout = ({x1, y1, x2, y2, label}) => (
  <g>
    <line x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={HD_RULE} strokeWidth="1.2" strokeDasharray="2 2"/>
    <circle cx={x2} cy={y2} r="11" fill={HD_RULE}/>
    <text x={x2} y={y2+4} textAnchor="middle"
          fontFamily={HD_F_MONO} fontWeight="600" fontSize="10"
          fill="#fff" letterSpacing="0.04em">{label}</text>
  </g>
);

const CalloutNote = ({n, t, b}) => (
  <div style={{display:'flex', gap:10, alignItems:'flex-start'}}>
    <div style={{width:22, height:22, borderRadius:'50%', background:HD_RULE,
                  color:'#fff', display:'flex', alignItems:'center',
                  justifyContent:'center', fontFamily:HD_F_MONO, fontSize:10,
                  fontWeight:600, flexShrink:0, marginTop:1}}>{n}</div>
    <div>
      <div style={{fontFamily:HD_F_DISP, fontWeight:600, fontSize:13.5}}>{t}</div>
      <div style={{fontFamily:HD_F_SER, fontStyle:'italic', fontSize:13,
                    color:HD_INK2, lineHeight:1.4, marginTop:2}}>{b}</div>
    </div>
  </div>
);

window.HdAnatomy = HdAnatomy;
