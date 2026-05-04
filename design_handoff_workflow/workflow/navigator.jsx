// workflow/navigator.jsx — workflow navigator components.
// Two treatments, both rendered above the map. Use either in isolation or both.

// ── A. Top rail grouped by family ───────────────────────────────────
const NavTopRail = ({workflows, activeId, onPick}) => {
  const families = {};
  workflows.forEach(w => { (families[w.family] ||= []).push(w); });
  const familyOrder = ['coding','pm','maintenance'];
  const familyLabel = {coding:'CODING', pm:'PM', maintenance:'MAINTENANCE'};
  return (
    <div style={{display:'flex', alignItems:'stretch', gap:0, marginBottom:14,
                 background:Wf_PAPER2, border:`1px solid ${Wf_EDGE}`, borderRadius:4}}>
      {familyOrder.filter(f=>families[f]).map((f, i) => (
        <div key={f} style={{flex:'1 1 0', borderLeft: i>0 ? `1px dashed ${Wf_EDGE}`:'none'}}>
          <div style={{padding:'8px 14px 0', fontFamily:"'Geist Mono', monospace",
                       fontSize:9.5, letterSpacing:'0.18em', color:Wf_INK3}}>
            FAMILY · {familyLabel[f]}
          </div>
          <div style={{display:'flex', flexWrap:'wrap', gap:0, padding:'6px 6px 8px'}}>
            {families[f].map(w => {
              const active = w.id === activeId;
              return (
                <button key={w.id} onClick={()=>onPick?.(w.id)}
                  style={{cursor:'pointer', textAlign:'left',
                          padding:'8px 10px', margin:0, background: active?Wf_INK:Wf_PAPER,
                          color: active?Wf_PAPER:Wf_INK,
                          border:`1px solid ${active?Wf_INK:Wf_EDGE}`,
                          fontFamily:"'Bricolage Grotesque', sans-serif",
                          fontSize:12.5, fontWeight:500, lineHeight:1.15,
                          minWidth:160, marginRight:6, marginBottom:4,
                          display:'flex', flexDirection:'column', gap:2}}>
                  <span style={{display:'flex', alignItems:'center', gap:6}}>
                    <span style={{width:8, height:8, borderRadius:'50%',
                                  background: window.ACTOR_COLOR[w.actor] || Wf_INK}}/>
                    {w.label}
                  </span>
                  <span style={{fontFamily:"'Geist Mono', monospace", fontSize:9.5,
                                color: active?'#d8d2c2':Wf_INK3, letterSpacing:'0.06em'}}>
                    {w.statuses.length} st · {w.routes.length} rt
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

// ── B. Mini-territory grid (workflow-of-workflows) ──────────────────
const NavMinimap = ({workflows, activeId, onPick}) => {
  const cardW = 188, cardH = 128;
  return (
    <div style={{marginBottom:14}}>
      <div style={{display:'flex', alignItems:'center', justifyContent:'space-between',
                   marginBottom:6}}>
        <WfEyebrow>workflow ecosystem · all {workflows.length}</WfEyebrow>
        <span style={{fontFamily:"'Instrument Serif', serif", fontStyle:'italic',
                      fontSize:13, color:Wf_INK3}}>
          tripwire is many workflows, not one lifecycle.
        </span>
      </div>
      <div style={{display:'grid',
                   gridTemplateColumns:`repeat(${Math.min(workflows.length, 6)}, 1fr)`,
                   gap:8, padding:8, background:Wf_PAPER2,
                   border:`1px solid ${Wf_EDGE}`, borderRadius:4}}>
        {workflows.map(w => (
          <button key={w.id} onClick={()=>onPick?.(w.id)}
            style={{cursor:'pointer', textAlign:'left', padding:0, margin:0,
                    background:'none', border:0}}>
            <NavMinimapCard w={w} active={w.id === activeId} cardW={cardW} cardH={cardH}/>
          </button>
        ))}
      </div>
    </div>
  );
};

const NavMinimapCard = ({w, active, cardW, cardH}) => {
  // Tiny svg territory: row of bands + sample arc.
  const W = cardW, H = cardH;
  const bandY = 50, bandH = 40;
  const padX = 10;
  const usable = W - padX*2;
  const bw = usable / w.statuses.length;
  const accent = window.ACTOR_COLOR[w.actor] || Wf_INK;
  return (
    <div style={{
      background: active ? Wf_INK : Wf_PAPER,
      color: active ? Wf_PAPER : Wf_INK,
      border:`1.5px solid ${active ? Wf_INK : Wf_EDGE}`,
      width:'100%', height:cardH, position:'relative',
      display:'flex', flexDirection:'column',
      transition:'all 0.1s'}}>
      {/* heading */}
      <div style={{padding:'8px 10px 4px', display:'flex', justifyContent:'space-between',
                   alignItems:'flex-start', gap:6}}>
        <div>
          <div style={{fontFamily:"'Bricolage Grotesque', sans-serif", fontSize:12,
                       fontWeight:600, letterSpacing:'-0.01em'}}>{w.label}</div>
          <div style={{fontFamily:"'Geist Mono', monospace", fontSize:9,
                       color:active?'#d8d2c2':Wf_INK3, letterSpacing:'0.04em', marginTop:1}}>
            {w.family} · {w.actor}
          </div>
        </div>
        <div style={{width:8, height:8, borderRadius:'50%', background:accent,
                     marginTop:3, flexShrink:0}}/>
      </div>
      {/* mini territory */}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={cardH-44}
           preserveAspectRatio="none" style={{display:'block'}}>
        {w.statuses.map((s,i) => (
          <rect key={s.id} x={padX + i*bw} y={bandY} width={bw-1} height={bandH}
                fill={i%2===0 ? (active?'#2a2723':'#efebde') : (active?'#1f1d1a':'#e8e2cf')}
                opacity="0.95"/>
        ))}
        {w.routes.slice(0,4).map((r, i) => {
          const fi = w.statuses.findIndex(s => s.id === r.from);
          const ti = w.statuses.findIndex(s => s.id === r.to);
          if (fi < 0 || ti < 0) return null;
          const fx = padX + fi*bw + bw/2;
          const tx = padX + ti*bw + bw/2;
          const y = bandY + bandH/2;
          if (r.kind === 'return') {
            return <path key={r.id} d={`M ${fx} ${y} Q ${(fx+tx)/2} ${y+22}, ${tx} ${y}`}
                         stroke={accent} strokeWidth="1.4" fill="none"/>;
          }
          return <path key={r.id} d={`M ${fx} ${y-3-i*1.5} Q ${(fx+tx)/2} ${y-12-i*2}, ${tx} ${y-3-i*1.5}`}
                       stroke={accent} strokeWidth="1.4" fill="none"
                       opacity={0.95-i*0.15}/>;
        })}
      </svg>
      {/* footer counts */}
      <div style={{padding:'2px 10px 8px', fontFamily:"'Geist Mono', monospace",
                   fontSize:9, letterSpacing:'0.04em',
                   color:active?'#d8d2c2':Wf_INK3,
                   display:'flex', gap:8}}>
        <span>{w.statuses.length} statuses</span>
        <span>·</span>
        <span>{w.routes.length} routes</span>
        <span>·</span>
        <span>{w.routes.filter(r=>r.kind==='return').length} returns</span>
      </div>
    </div>
  );
};

Object.assign(window, { NavTopRail, NavMinimap, NavMinimapCard });
