// workflow/page.jsx — page assembly: navigator + chart in two gate modes.
const {useState: useStateP} = React;

const WorkflowPage = ({initialWorkflowId='coding-session', gateMode='lock'}) => {
  const workflows = window.WORKFLOWS;
  const [activeId, setActiveId] = useStateP(initialWorkflowId);
  const wf = workflows.find(w => w.id === activeId) || workflows[0];

  return (
    <div style={{height:'100%', overflow:'auto', background:Wf_PAPER}}>
      <div style={{padding:'18px 28px 0'}}>
        <NavTopRail workflows={workflows} activeId={activeId} onPick={setActiveId}/>
        <div style={{display:'flex', alignItems:'flex-end', justifyContent:'space-between',
                     gap:24, marginBottom:8}}>
          <div>
            <WfEyebrow>workflow · {wf.id}</WfEyebrow>
            <h1 style={{margin:'4px 0 0', fontFamily:"'Bricolage Grotesque', sans-serif",
                        fontWeight:600, fontSize:34, lineHeight:1, letterSpacing:'-0.025em', color:Wf_INK}}>
              {wf.label}
            </h1>
            <p style={{margin:'6px 0 0', fontFamily:"'Instrument Serif', serif", fontStyle:'italic',
                       fontSize:15, color:Wf_INK2, maxWidth:780, lineHeight:1.4}}>{wf.blurb}</p>
          </div>
          <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:6,
                       fontFamily:"'Geist Mono', monospace", fontSize:11, color:Wf_INK3}}>
            <span>workflow.yaml · v0.9.6 · {gateMode === 'lock' ? 'gate-as-lock' : 'gate-as-diamond'}</span>
            <div style={{display:'flex', gap:6}}>
              <WfStamp tone="rule">DEFINITION</WfStamp>
              <WfStamp tone="mute">{wf.statuses.length} ST · {wf.routes.length} RT</WfStamp>
            </div>
          </div>
        </div>
        <WfActorLegendInline/>
      </div>
      <div style={{padding:'10px 28px 28px'}}>
        <Flowchart workflow={wf} gateMode={gateMode}
                   initialOpenGateOn={wf.id==='coding-session' ? 't-queued-to-executing' : null}/>
      </div>
    </div>
  );
};

const WfActorLegendInline = () => (
  <div style={{display:'flex', gap:14, alignItems:'center', flexWrap:'wrap', marginTop:8,
               fontFamily:"'Geist Mono', monospace", fontSize:10, color:Wf_INK2,
               padding:'8px 12px', background:Wf_PAPER2, border:`1px solid ${Wf_EDGE}`}}>
    <WfEyebrow>actors</WfEyebrow>
    {Object.entries(window.ACTOR_COLOR).map(([k,c]) => (
      <span key={k} style={{display:'inline-flex', alignItems:'center', gap:6}}>
        <span style={{width:18, height:3, background:c}}/>
        {k}
      </span>
    ))}
    <span style={{flex:1}}/>
    <WfEyebrow>route</WfEyebrow>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="10"><path d="M2 5 L34 5" stroke={Wf_INK} strokeWidth="2"/></svg>forward
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="10"><path d="M2 5 L34 5" stroke={Wf_INK} strokeWidth="2" strokeDasharray="7 5"/></svg>return
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="36" height="10"><path d="M2 5 L34 5" stroke={Wf_INK} strokeWidth="2" strokeDasharray="10 4 2 4"/></svg>side
    </span>
    <WfEyebrow>markers</WfEyebrow>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="14" height="14"><rect x="2" y="6" width="10" height="6" stroke={Wf_GATE} strokeWidth="1.4" fill="none"/><path d="M4 6 V4 a3 3 0 0 1 6 0 V6" stroke={Wf_GATE} strokeWidth="1.4" fill="none"/></svg>
      gate cluster
    </span>
    <span style={{display:'inline-flex', alignItems:'center', gap:6}}>
      <svg width="14" height="14"><rect x="2" y="2" width="10" height="10" rx="3" stroke={Wf_TRIP} strokeWidth="1.4" fill="none"/><text x="7" y="10" textAnchor="middle" fontSize="9" fontWeight="700" fill={Wf_TRIP}>!</text></svg>
      jit prompt
    </span>
  </div>
);

window.WorkflowPage = WorkflowPage;
