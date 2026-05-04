// design_handoff_workflow/handoff/cover.jsx — cover + intro
const HdCover = () => (
  <section style={{padding:'88px 0 32px', maxWidth:980, margin:'0 auto'}}>
    <div style={{borderTop:`2px solid ${HD_INK}`, paddingTop:14,
                  display:'flex', justifyContent:'space-between', alignItems:'flex-end',
                  fontFamily:HD_F_MONO, fontSize:11, letterSpacing:'0.18em',
                  color:HD_INK3, textTransform:'uppercase'}}>
      <span>Tripwire · workflow.yaml v0.9.6</span>
      <span>handoff · v1 · territory map</span>
    </div>

    <div style={{margin:'72px 0 0'}}>
      <HdEyebrow color={HD_RULE}>Spec · for engineering</HdEyebrow>
      <h1 style={{margin:'14px 0 0', fontFamily:HD_F_DISP, fontWeight:600,
                   fontSize:78, lineHeight:0.98, letterSpacing:'-0.035em', color:HD_INK,
                   maxWidth:920}}>
        The Workflow page,<br/>
        <em style={{fontFamily:HD_F_SER, fontWeight:400, fontStyle:'italic'}}>
          stamped, dated, signed.
        </em>
      </h1>
      <p style={{margin:'24px 0 0', maxWidth:780, fontFamily:HD_F_SER, fontStyle:'italic',
                  fontSize:22, lineHeight:1.4, color:HD_INK2}}>
        A new screen for the Tripwire dashboard that renders <Mono>workflow.yaml</Mono> as
        a territory-and-routes map. Statuses are bands. Transitions are colour-keyed
        boxes. Validators are locks. Just-in-time prompts are flares. Skills ride along.
        Artifacts get filed.
      </p>
    </div>

    <div style={{marginTop:48, display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:0,
                  borderTop:`1px solid ${HD_INK}`, borderBottom:`1px solid ${HD_INK}`}}>
      <HdMeta label="version"   value="V1 · territory" detail="bands + lanes + proof shelf" />
      <HdMeta label="audience"  value="Frontend engineering" detail="React 18 / Vite / Tailwind 4" />
      <HdMeta label="fidelity"  value="High · for V1" detail="canonical workflow finalised" />
    </div>

    <div style={{marginTop:32, display:'flex', gap:8, flexWrap:'wrap'}}>
      <HdStamp tone="rule">spec</HdStamp>
      <HdStamp tone="ink">tripwire / workflow</HdStamp>
      <HdStamp tone="mute">v0.9.6</HdStamp>
      <HdStamp tone="info">six workflows</HdStamp>
      <HdStamp tone="gate">gate-as-diamond</HdStamp>
      <HdStamp tone="trip">jit prompts</HdStamp>
    </div>

    <p style={{marginTop:48, maxWidth:760, fontFamily:HD_F_TEXT, fontSize:16,
                lineHeight:1.6, color:HD_INK}}>
      This document is the visual spec — anatomy, element measurements, data schema,
      behaviours. Pair it with <Mono>README.md</Mono> (project notes &amp; open
      questions) and <Mono>Tripwire — Workflow.html</Mono> (the live prototype on the
      design canvas). Production code goes through the redesign tokens already documented
      in <Mono>design_handoff_tripwire_redesign/</Mono>; this doc adds nothing to the
      palette.
    </p>
  </section>
);

const HdMeta = ({label, value, detail}) => (
  <div style={{padding:'18px 22px', borderRight:`1px solid ${HD_EDGE}`}}>
    <div style={{fontFamily:HD_F_MONO, fontSize:9.5, letterSpacing:'0.2em',
                  color:HD_INK3, textTransform:'uppercase', marginBottom:6}}>{label}</div>
    <div style={{fontFamily:HD_F_DISP, fontSize:18, fontWeight:600,
                  letterSpacing:'-0.01em', color:HD_INK}}>{value}</div>
    <div style={{fontFamily:HD_F_SER, fontStyle:'italic', fontSize:13,
                  color:HD_INK2, marginTop:4}}>{detail}</div>
  </div>
);

window.HdCover = HdCover;
