// workflow/atoms.jsx — small shared atoms used across all workflow variations.
const Wf_PAPER = '#f0eee9';
const Wf_PAPER2 = '#faf8f3';
const Wf_PAPER3 = '#e8e4dc';
const Wf_EDGE = '#c9bfae';
const Wf_INK = '#1a1815';
const Wf_INK2 = '#4a453d';
const Wf_INK3 = '#7a7368';
const Wf_RULE = '#c83d2e';
const Wf_GATE = '#2d5a3d';
const Wf_TRIP = '#b8741a';
const Wf_INFO = '#2d3a7c';

const WfEyebrow = ({children, color}) => (
  <span style={{
    fontFamily:"'Geist Mono', monospace", fontSize:10, letterSpacing:'0.18em',
    textTransform:'uppercase', color: color || Wf_INK3,
  }}>{children}</span>
);

const WfStamp = ({children, tone='ink', size=10}) => {
  const tones = {
    ink:   { fg:Wf_INK,  bg:'transparent', bd:Wf_INK  },
    rule:  { fg:Wf_RULE, bg:'transparent', bd:Wf_RULE },
    gate:  { fg:Wf_GATE, bg:'transparent', bd:Wf_GATE },
    trip:  { fg:Wf_TRIP, bg:'transparent', bd:Wf_TRIP },
    info:  { fg:Wf_INFO, bg:'transparent', bd:Wf_INFO },
    mute:  { fg:Wf_INK3, bg:'transparent', bd:Wf_EDGE },
    inkSolid:{fg:Wf_PAPER,bg:Wf_INK, bd:Wf_INK},
    ruleSolid:{fg:'#fff', bg:Wf_RULE, bd:Wf_RULE},
  };
  const t = tones[tone] || tones.ink;
  return (
    <span style={{
      display:'inline-block', fontFamily:"'Geist Mono', monospace",
      fontWeight:600, fontSize:size, letterSpacing:'0.06em',
      padding:'2px 6px', border:`1px solid ${t.bd}`, color:t.fg,
      background:t.bg, textTransform:'uppercase',
    }}>{children}</span>
  );
};

// Marker-arrow defs reused by every SVG layout
const WfArrowDefs = () => (
  <defs>
    {Object.entries(window.ACTOR_COLOR).map(([k,c]) => (
      <marker key={k} id={`wf-arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 Z" fill={c} />
      </marker>
    ))}
    <marker id="wf-arrow-mute" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 Z" fill={Wf_INK3} />
    </marker>
    <pattern id="wf-paper-grid" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M 20 0 L 0 0 0 20" fill="none" stroke={Wf_INK} strokeWidth="0.5" opacity="0.04"/>
    </pattern>
  </defs>
);

// Page header — shared across variations
const WfPageHeader = ({chapter, title, sub}) => (
  <div style={{display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:24, marginBottom:14}}>
    <div>
      <WfEyebrow>{chapter}</WfEyebrow>
      <h1 style={{margin:'6px 0 0', fontFamily:"'Bricolage Grotesque', sans-serif",
                  fontWeight:600, fontSize:36, lineHeight:1, letterSpacing:'-0.025em', color:Wf_INK}}>{title}</h1>
      <p style={{margin:'8px 0 0', fontFamily:"'Instrument Serif', serif", fontStyle:'italic',
                 fontSize:16, color:Wf_INK2, maxWidth:780, lineHeight:1.4}}>{sub}</p>
    </div>
    <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:6,
                 fontFamily:"'Geist Mono', monospace", fontSize:11, color:Wf_INK3}}>
      <span><span style={{color:Wf_INK3}}>workflow.yaml</span> · v0.9.6</span>
      <div style={{display:'flex', gap:6}}>
        <WfStamp tone="rule">DEFINITION</WfStamp>
        <WfStamp tone="mute">6 WORKFLOWS</WfStamp>
      </div>
    </div>
  </div>
);

// Actor legend
const WfActorLegend = () => (
  <div style={{display:'flex', gap:14, alignItems:'center', flexWrap:'wrap',
               fontFamily:"'Geist Mono', monospace", fontSize:10.5, color:Wf_INK2,
               padding:'10px 12px', background:Wf_PAPER2, border:`1px solid ${Wf_EDGE}`, borderRadius:4}}>
    <WfEyebrow>actors</WfEyebrow>
    {Object.entries(window.ACTOR_COLOR).map(([k,c]) => (
      <span key={k} style={{display:'inline-flex', alignItems:'center', gap:6}}>
        <svg width="32" height="10"><path d="M2 5 L30 5" stroke={c} strokeWidth="2.4" markerEnd={`url(#wf-arrow-${k})`}/>
          <WfArrowDefs/>
        </svg>
        {k}
      </span>
    ))}
    <span style={{flex:1}} />
    <WfEyebrow>route kinds</WfEyebrow>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="14"><path d="M2 7 L34 7" stroke={Wf_INK} strokeWidth="2"/></svg>forward
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="14"><path d="M2 4 Q 18 14, 34 4" stroke={Wf_INK} strokeWidth="2" fill="none" strokeDasharray="6 4"/></svg>return
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="14"><path d="M2 7 L34 7" stroke={Wf_INK} strokeWidth="2" strokeDasharray="10 5 2 5"/></svg>side
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="14" height="14"><circle cx="7" cy="7" r="5" fill={Wf_INK}/></svg>terminal
    </span>
  </div>
);

// Marker glyphs (shared)
const WfGateGlyph = ({size=14, color=Wf_GATE}) => (
  <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
    <rect x="3" y="6" width="8" height="6" stroke={color} strokeWidth="1.4"/>
    <path d="M5 6 V4.5 a2 2 0 0 1 4 0 V6" stroke={color} strokeWidth="1.4" fill="none"/>
  </svg>
);
const WfJitGlyph = ({size=14, color=Wf_TRIP}) => (
  <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
    <path d="M7 1 L7 8 M7 11 L7 12.5" stroke={color} strokeWidth="1.6" strokeLinecap="round"/>
    <circle cx="7" cy="7" r="5.5" stroke={color} strokeWidth="1.2" fill={Wf_PAPER2}/>
  </svg>
);
const WfCmdGlyph = ({size=14, color=Wf_INK}) => (
  <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
    <rect x="1.5" y="2.5" width="11" height="9" stroke={color} strokeWidth="1.2"/>
    <path d="M3.5 6.5 L5 8 L3.5 9.5 M6.5 9.5 L9 9.5" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
  </svg>
);
const WfSkillGlyph = ({size=14, color=Wf_INFO}) => (
  <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
    <path d="M2 3 H12 V11 H2 Z M2 3 L7 6 L12 3" stroke={color} strokeWidth="1.2" fill="none"/>
  </svg>
);
const WfArtGlyph = ({size=14, color=Wf_INK}) => (
  <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
    <path d="M3 1.5 H8 L11 4.5 V12.5 H3 Z" stroke={color} strokeWidth="1.2" strokeDasharray="2 2"/>
    <path d="M8 1.5 V4.5 H11" stroke={color} strokeWidth="1.2"/>
  </svg>
);

Object.assign(window, {
  Wf_PAPER, Wf_PAPER2, Wf_PAPER3, Wf_EDGE, Wf_INK, Wf_INK2, Wf_INK3, Wf_RULE, Wf_GATE, Wf_TRIP, Wf_INFO,
  WfEyebrow, WfStamp, WfArrowDefs, WfPageHeader, WfActorLegend,
  WfGateGlyph, WfJitGlyph, WfCmdGlyph, WfSkillGlyph, WfArtGlyph,
});
