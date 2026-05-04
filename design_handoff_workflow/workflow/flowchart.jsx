// workflow/flowchart.jsx — renderer using lane-allocated layout.
const { useState } = React;

const FlowMarker = () => (
  <defs>
    {Object.entries(window.ACTOR_COLOR).map(([k,c]) => (
      <marker key={k} id={`fc-arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 Z" fill={c} />
      </marker>
    ))}
    <pattern id="fc-paper-grid" width="24" height="24" patternUnits="userSpaceOnUse">
      <path d="M 24 0 L 0 0 0 24" fill="none" stroke={Wf_INK} strokeWidth="0.5" opacity="0.035"/>
    </pattern>
  </defs>
);

// transition node
const TransitionNode = ({tx}) => {
  if (tx.kind === 'branch') return <BranchDiamond tx={tx}/>;
  const r = tx.route;
  const c = window.ACTOR_COLOR[r.actor];
  const skills = r.skills || [];

  return (
    <g transform={`translate(${tx.cx} ${tx.cy})`}>
      {/* skill ribbon — STACKED above the box, one skill per line, hard-truncated */}
      {skills.length > 0 && (
        <g>
          {skills.slice(0,3).map((s, i) => {
            const cond = window.skillCondition?.(r.id, s);
            // hard truncate to fit within TX_W - 8 (~160px)
            const short = s.length > 14 ? s.slice(0,12)+'…' : s;
            return (
              <text key={s} x={-TX_W/2 + 4} y={-TX_H/2 - 14 - (skills.length-1-i)*11}
                    fontFamily="'Geist Mono', monospace" fontSize="8.5"
                    fill={Wf_INFO} letterSpacing="0.02em">
                ▸ <tspan style={cond ? {textDecoration:'underline', textDecorationStyle:'dotted'} : {}}>{short}</tspan>
                {cond ? '?' : ''}
              </text>
            );
          })}
        </g>
      )}

      {/* main box */}
      <rect x={-TX_W/2} y={-TX_H/2} width={TX_W} height={TX_H}
            fill={Wf_PAPER} stroke={c} strokeWidth="1.6" rx="3"/>
      <rect x={-TX_W/2} y={-TX_H/2} width="4" height={TX_H} fill={c}/>

      {r.command && (
        <text x={-TX_W/2 + 12} y={-TX_H/2 + 14}
              fontFamily="'Geist Mono', monospace" fontSize="9.5"
              fill={Wf_INK3} letterSpacing="0.04em">▷ {r.command}</text>
      )}
      <text x={-TX_W/2 + 12} y={r.command ? -TX_H/2 + 30 : -2}
            fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="600"
            fontSize="13" fill={Wf_INK} letterSpacing="-0.005em">
        {r.label}
      </text>
      <text x={TX_W/2 - 8} y={TX_H/2 - 8} textAnchor="end"
            fontFamily="'Geist Mono', monospace" fontSize="8.5" fontWeight="600"
            fill={c} letterSpacing="0.06em">
        {(window.ACTOR_LABEL[r.actor]||r.actor).toUpperCase()}
      </text>
    </g>
  );
};

const BranchDiamond = ({tx}) => {
  const c = window.ACTOR_COLOR[tx.actor] || Wf_INK;
  const half = 32;
  const wide = 60;
  return (
    <g transform={`translate(${tx.cx} ${tx.cy})`}>
      <text x="0" y={-half - 12} textAnchor="middle"
            fontFamily="'Geist Mono', monospace" fontSize="9"
            fill={Wf_INFO}>▸ project-manager · verification</text>
      <polygon points={`0,${-half} ${wide},0 0,${half} ${-wide},0`}
               fill={Wf_PAPER} stroke={c} strokeWidth="1.6"/>
      <text x="0" y="-2" textAnchor="middle" fontFamily="'Geist Mono', monospace"
            fontSize="9.5" fill={Wf_INK3}>▷ {tx.command}</text>
      <text x="0" y="14" textAnchor="middle"
            fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="600"
            fontSize="12" fill={Wf_INK}>decision</text>
    </g>
  );
};

// Gate badge — RENDERED INSIDE the transition node at the top-right corner.
// This eliminates horizontal collision with neighboring boxes.
const GateBadge = ({tx, opened, onToggle}) => {
  if (tx.kind === 'branch') return null;
  const r = tx.route;
  const valN = (r.controls.validators?.length||0) + (r.controls.prompt_checks?.length||0);
  if (valN === 0) return null;
  // place badge INSIDE box, top-right
  const bx = tx.cx + TX_W/2 - 44;
  const by = tx.cy - TX_H/2 + 4;
  return (
    <g transform={`translate(${bx} ${by})`} style={{cursor:'pointer'}}
       onClick={(e)=>{e.stopPropagation(); onToggle?.(tx.id);}}>
      <rect x="0" y="0" width="40" height="14" fill={Wf_PAPER2}
            stroke={Wf_GATE} strokeWidth="1"/>
      <path d="M 4 9 V 7 a2 2 0 0 1 4 0 V 9" stroke={Wf_GATE} strokeWidth="1" fill="none"/>
      <rect x="3" y="9" width="6" height="4" stroke={Wf_GATE} strokeWidth="1" fill="none"/>
      <text x="14" y="10" fontFamily="'Geist Mono', monospace" fontSize="9"
            fontWeight="600" fill={Wf_GATE} letterSpacing="0.04em">×{valN}</text>
    </g>
  );
};

const GatePanel = ({tx, w, h, onClose}) => {
  if (!tx) return null;
  const r = tx.route;
  const rows = window.describeGateContents(r);
  if (rows.length === 0) return null;
  return (
    <div style={{
      position:'absolute',
      left: `${(tx.cx)/w*100}%`, top: `${(tx.cy + 50)/h*100}%`,
      transform:'translateX(-50%)', minWidth:280, maxWidth:340,
      background:Wf_PAPER, border:`1.5px solid ${Wf_GATE}`,
      boxShadow:'0 14px 30px rgba(26,24,21,0.12)',
      padding:'10px 12px', zIndex:30, fontSize:12, color:Wf_INK,
    }}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6}}>
        <span style={{fontFamily:"'Geist Mono', monospace", fontSize:10,
                       letterSpacing:'0.18em', color:Wf_GATE}}>GATE · {rows.length} CHECKS</span>
        <button onClick={onClose} style={{cursor:'pointer', border:0, background:'none',
                                          fontFamily:"'Geist Mono', monospace", fontSize:11, color:Wf_INK3}}>×</button>
      </div>
      <div style={{fontFamily:"'Bricolage Grotesque', sans-serif", fontWeight:600, fontSize:13, marginBottom:8}}>
        on {r.label}
      </div>
      <div style={{display:'flex', flexDirection:'column', gap:5, maxHeight:280, overflow:'auto'}}>
        {rows.map((row, i) => (
          <div key={row.id+'-'+i} style={{display:'flex', gap:8,
                                           padding:'4px 0', borderTop: i===0?'none':`1px dashed ${Wf_EDGE}`}}>
            <span style={{fontFamily:"'Geist Mono', monospace", fontSize:9,
                          color: row.kind==='validator'?Wf_GATE:Wf_INFO,
                          letterSpacing:'0.04em', flexShrink:0, width:28, textTransform:'uppercase'}}>
              {row.kind==='validator'?'val':'pmt'}
            </span>
            <div style={{flex:1, minWidth:0}}>
              <div style={{fontFamily:"'Geist Mono', monospace", fontSize:10.5, color:Wf_INK}}>{row.label}</div>
              {row.blurb && <div style={{fontFamily:"'Instrument Serif', serif", fontStyle:'italic',
                                          fontSize:11.5, color:Wf_INK2, marginTop:1}}>{row.blurb}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const JitNode = ({jit}) => (
  <g transform={`translate(${jit.x} ${jit.y})`}>
    <rect x="-13" y="-13" width="26" height="26" rx="6" ry="6"
          fill={Wf_PAPER} stroke={Wf_TRIP} strokeWidth="1.5"/>
    <text x="0" y="4" textAnchor="middle" fontFamily="'Geist Mono', monospace"
          fontSize="13" fontWeight="700" fill={Wf_TRIP}>!</text>
    <text x="0" y="28" textAnchor="middle" fontFamily="'Geist Mono', monospace" fontSize="8.5"
          fill={Wf_INK2} letterSpacing="0.02em">{jit.label}</text>
  </g>
);

const ArtifactTile = ({label, x, y}) => (
  <g transform={`translate(${x} ${y})`}>
    <g transform="translate(-58, 0)">
      <path d={`M 0 0 H 100 L 116 12 V 30 H 0 Z`} fill={Wf_PAPER}
            stroke={Wf_INK3} strokeDasharray="3 2" strokeWidth="0.9"/>
      <path d="M 100 0 V 12 H 116" fill="none" stroke={Wf_INK3} strokeWidth="0.9" strokeDasharray="3 2"/>
      <text x="58" y="20" textAnchor="middle" fontFamily="'Geist Mono', monospace"
            fontSize="9.5" fill={Wf_INK2}>◫ {label}</text>
    </g>
  </g>
);

const PortNode = ({port}) => (
  <g transform={`translate(${port.x} ${port.y})`}>
    <circle r="9" fill={port.kind==='sink'?Wf_INK:Wf_PAPER}
            stroke={Wf_INK} strokeWidth="1.6"/>
    {port.kind === 'source' && <circle r="2.5" fill={Wf_INK}/>}
    <text x={port.kind==='source'?-14:14}
          y="3" textAnchor={port.kind==='source'?'end':'start'}
          fontFamily="'Geist Mono', monospace" fontSize="10"
          fill={Wf_INK2} letterSpacing="0.04em">{port.label}</text>
    <text x={port.kind==='source'?-14:14}
          y="16" textAnchor={port.kind==='source'?'end':'start'}
          fontFamily="'Geist Mono', monospace" fontSize="8"
          fill={Wf_INK3} letterSpacing="0.12em">{port.kind.toUpperCase()}</text>
  </g>
);

const Flowchart = ({workflow, gateMode='lock'}) => {
  const layout = window.layoutWorkflow(workflow, { gateMode });
  const [openedGate, setOpenedGate] = useState(null);
  const { width, height, regions, transitions, edges, jits, ports, mainY, proofTop } = layout;
  const openedTx = openedGate ? transitions.find(t => t.id === openedGate) : null;

  return (
    <div style={{position:'relative', width:'100%'}}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%"
           preserveAspectRatio="xMidYMid meet" style={{display:'block'}}>
        <FlowMarker/>
        <rect width={width} height={height} fill={Wf_PAPER}/>
        <rect width={width} height={height} fill="url(#fc-paper-grid)"/>

        {/* compass */}
        <g fontFamily="'Geist Mono', monospace" fontSize="9.5" fill={Wf_INK3} letterSpacing="0.18em">
          <text x="40" y="28">WEST · INTENT</text>
          <text x={width/2} y="28" textAnchor="middle">NORTH · CONTROL</text>
          <text x={width-40} y="28" textAnchor="end">EAST · CLOSURE</text>
          <text x={width/2} y={height-12} textAnchor="middle">SOUTH · PROOF</text>
        </g>

        {/* status REGIONS */}
        {regions.map((r, i) => (
          <g key={r.id}>
            <rect x={r.x} y={r.y} width={r.w} height={r.h}
                  fill={i%2===0 ? '#efebde' : '#e8e2cf'}
                  stroke={Wf_EDGE} strokeWidth="0.7" strokeOpacity="0.7"/>
            <text x={r.x + 12} y={r.y + 22}
                  fontFamily="'Geist Mono', monospace" fontSize="9.5"
                  fill={Wf_INK3} letterSpacing="0.18em">
              {String(i+1).padStart(2,'0')} · STATUS
            </text>
            <text x={r.x + 12} y={r.y + 48}
                  fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="600"
                  fontSize="22" fill={Wf_INK} letterSpacing="-0.015em">{r.id}</text>
            <text x={r.x + 12} y={r.y + 68}
                  fontFamily="'Instrument Serif', serif" fontStyle="italic"
                  fontSize="13" fill={Wf_INK2}>{r.blurb}</text>
            {r.terminal && <circle cx={r.x + r.w - 14} cy={r.y + 14} r="6" fill={Wf_INK}/>}

            {/* divider line between status header and lane area */}
            <line x1={r.x+8} y1={r.y + 80} x2={r.x + r.w - 8} y2={r.y + 80}
                  stroke={Wf_EDGE} strokeOpacity="0.5"/>

            {/* divider line marking start of proof shelf */}
            <line x1={r.x+8} y1={proofTop - 8} x2={r.x + r.w - 8} y2={proofTop - 8}
                  stroke={Wf_EDGE} strokeOpacity="0.45" strokeDasharray="3 4"/>
            <text x={r.x + 12} y={proofTop + 6}
                  fontFamily="'Geist Mono', monospace" fontSize="8.5"
                  fill={Wf_INK3} letterSpacing="0.18em">PROOF SHELF</text>
          </g>
        ))}
        {regions.slice(1).map(r => (
          <line key={`bd-${r.id}`} x1={r.x} y1={r.y} x2={r.x} y2={r.y+r.h}
                stroke={Wf_EDGE} strokeWidth="0.9" strokeOpacity="0.55"/>
        ))}

        {/* main line guide (subtle) */}
        <line x1={regions[0].x + 8} y1={mainY} x2={regions[regions.length-1].x + regions[regions.length-1].w - 8} y2={mainY}
              stroke={Wf_EDGE} strokeOpacity="0.4" strokeDasharray="2 6"/>

        {/* edges */}
        {edges.map(e => {
          const c = window.ACTOR_COLOR[e.actor] || Wf_INK;
          const dash = e.kind==='return' ? '7 5' :
                       e.kind==='side'   ? '10 4 2 4' :
                       e.kind==='loop'   ? '4 4' : null;
          return (
            <path key={e.id} d={window.pathFromPoints(e.points, 9)}
                  stroke={c} strokeWidth="2" fill="none"
                  strokeDasharray={dash}
                  markerEnd={e.isOut ? `url(#fc-arrow-${e.actor})` : null}/>
          );
        })}

        {/* outcome labels for diamond outcomes */}
        {edges.filter(e=>e.outcomeLabel).map(e => {
          const p = e.points[Math.floor(e.points.length/2)];
          return (
            <g key={`ol-${e.id}`} transform={`translate(${p.x} ${p.y - 14})`}>
              <rect x="-32" y="-9" width="64" height="14" fill={Wf_PAPER} stroke={window.ACTOR_COLOR[e.actor]} strokeWidth="0.9"/>
              <text x="0" y="2" textAnchor="middle" fontFamily="'Geist Mono', monospace"
                    fontSize="9" fill={Wf_INK} letterSpacing="0.04em">{e.outcomeLabel}</text>
            </g>
          );
        })}

        {/* gate badges */}
        {gateMode === 'lock' && transitions.map(tx => (
          <GateBadge key={`g-${tx.id}`} tx={tx}
                     opened={openedGate===tx.id}
                     onToggle={(id)=>setOpenedGate(openedGate===id?null:id)}/>
        ))}

        {/* JITs */}
        {jits.map(j => <JitNode key={j.id} jit={j}/>)}

        {/* transitions */}
        {transitions.map(tx => <TransitionNode key={tx.id} tx={tx}/>)}

        {/* artifacts: one row at the bottom of each region */}
        {regions.map(r => {
          const arts = (r.artifacts?.produces || []);
          if (arts.length === 0) return null;
          const cellW = 130;
          const totalW = Math.min(arts.length, 1) * cellW;
          const startX = r.cx;
          return arts.slice(0,1).map((a,k) => (
            <ArtifactTile key={`art-${r.id}-${a.id}`} label={a.label}
                          x={startX} y={layout.artifactRowY}/>
          ));
        })}

        {/* ports */}
        {ports.map(p => <PortNode key={p.id} port={p}/>)}
      </svg>

      {openedTx && (
        <GatePanel tx={openedTx} w={width} h={height} onClose={()=>setOpenedGate(null)}/>
      )}
    </div>
  );
};

window.Flowchart = Flowchart;
