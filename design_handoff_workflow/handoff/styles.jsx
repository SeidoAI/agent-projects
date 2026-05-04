// design_handoff_workflow/handoff/styles.jsx — local helpers for the handoff doc
const HD_PAPER  = '#f0eee9';
const HD_PAPER2 = '#faf8f3';
const HD_PAPER3 = '#e8e4dc';
const HD_EDGE   = '#c9bfae';
const HD_EDGE2  = '#b5a991';
const HD_INK    = '#1a1815';
const HD_INK2   = '#4a453d';
const HD_INK3   = '#7a7368';
const HD_RULE   = '#c83d2e';
const HD_GATE   = '#2d5a3d';
const HD_TRIP   = '#b8741a';
const HD_INFO   = '#2d3a7c';

const HD_F_DISP = "'Bricolage Grotesque', sans-serif";
const HD_F_TEXT = "'Bricolage Grotesque', sans-serif";
const HD_F_SER  = "'Instrument Serif', serif";
const HD_F_MONO = "'Geist Mono', monospace";

// Section wrapper — establishes the page rhythm
const HdSection = ({eyebrow, title, sub, children, id}) => (
  <section id={id} style={{padding:'72px 0 0', maxWidth:980, margin:'0 auto'}}>
    <div style={{borderTop:`1px solid ${HD_INK}`, paddingTop:18}}>
      <div style={{fontFamily:HD_F_MONO, fontSize:11, letterSpacing:'0.22em',
                    textTransform:'uppercase', color:HD_INK3, marginBottom:8}}>{eyebrow}</div>
      <h2 style={{margin:0, fontFamily:HD_F_DISP, fontWeight:600, fontSize:42,
                   lineHeight:1.05, letterSpacing:'-0.025em', color:HD_INK}}>{title}</h2>
      {sub && (
        <p style={{margin:'10px 0 0', maxWidth:760, fontFamily:HD_F_SER, fontStyle:'italic',
                    fontSize:18, lineHeight:1.45, color:HD_INK2}}>{sub}</p>
      )}
    </div>
    <div style={{marginTop:32}}>{children}</div>
  </section>
);

// Eyebrow inline
const HdEyebrow = ({children, color}) => (
  <span style={{fontFamily:HD_F_MONO, fontSize:10, letterSpacing:'0.2em',
                 textTransform:'uppercase', color: color || HD_INK3}}>{children}</span>
);

// A "stamp" pill — borrowed pattern from the redesign tokens
const HdStamp = ({children, tone='ink', size=10}) => {
  const tones = {
    ink:  { fg:HD_INK,  bd:HD_INK },
    rule: { fg:HD_RULE, bd:HD_RULE },
    gate: { fg:HD_GATE, bd:HD_GATE },
    trip: { fg:HD_TRIP, bd:HD_TRIP },
    info: { fg:HD_INFO, bd:HD_INFO },
    mute: { fg:HD_INK3, bd:HD_EDGE },
  };
  const t = tones[tone] || tones.ink;
  return (
    <span style={{display:'inline-block', fontFamily:HD_F_MONO, fontWeight:600,
                   fontSize:size, letterSpacing:'0.06em', padding:'2px 6px',
                   border:`1px solid ${t.bd}`, color:t.fg, textTransform:'uppercase'}}>
      {children}
    </span>
  );
};

// Body copy
const HdBody = ({children, narrow}) => (
  <div style={{fontFamily:HD_F_TEXT, fontSize:15, lineHeight:1.6, color:HD_INK,
                maxWidth: narrow ? 680 : 820}}>{children}</div>
);

// Caption (italic margin note)
const HdCaption = ({children}) => (
  <div style={{fontFamily:HD_F_SER, fontStyle:'italic', fontSize:14,
                color:HD_INK2, lineHeight:1.5, marginTop:8}}>{children}</div>
);

// Mono text
const Mono = ({children, color}) => (
  <code style={{fontFamily:HD_F_MONO, fontSize:'0.9em', color: color || HD_INK,
                 background:'rgba(26,24,21,0.05)', padding:'1px 5px', borderRadius:2}}>
    {children}
  </code>
);

// A spec table — for element measurements
const HdSpecTable = ({rows}) => (
  <table style={{borderCollapse:'collapse', width:'100%', fontFamily:HD_F_TEXT, fontSize:13}}>
    <tbody>
      {rows.map((r, i) => (
        <tr key={i} style={{borderTop: i===0 ? `1px solid ${HD_INK}` : `1px dashed ${HD_EDGE}`}}>
          <td style={{padding:'10px 14px 10px 0', verticalAlign:'top', width:200,
                       fontFamily:HD_F_MONO, fontSize:11, letterSpacing:'0.04em',
                       color:HD_INK3, textTransform:'uppercase'}}>{r[0]}</td>
          <td style={{padding:'10px 0', verticalAlign:'top', color:HD_INK}}>{r[1]}</td>
        </tr>
      ))}
      <tr style={{borderTop:`1px solid ${HD_INK}`}}><td/><td/></tr>
    </tbody>
  </table>
);

// A "card" panel
const HdPanel = ({title, eyebrow, children, tone='neutral'}) => {
  const accent = tone === 'rule' ? HD_RULE : tone === 'gate' ? HD_GATE :
                 tone === 'trip' ? HD_TRIP : tone === 'info' ? HD_INFO : HD_INK;
  return (
    <div style={{background:HD_PAPER2, border:`1px solid ${HD_EDGE}`,
                  padding:'18px 22px', position:'relative'}}>
      <div style={{position:'absolute', left:0, top:0, bottom:0, width:3, background:accent}}/>
      {eyebrow && <HdEyebrow color={accent}>{eyebrow}</HdEyebrow>}
      {title && (
        <h3 style={{margin: eyebrow ? '6px 0 8px' : '0 0 8px',
                     fontFamily:HD_F_DISP, fontWeight:600, fontSize:20,
                     letterSpacing:'-0.01em', color:HD_INK}}>{title}</h3>
      )}
      <div style={{fontFamily:HD_F_TEXT, fontSize:14, lineHeight:1.55, color:HD_INK}}>{children}</div>
    </div>
  );
};

// Code block
const HdCode = ({children, lang}) => (
  <pre style={{fontFamily:HD_F_MONO, fontSize:12.5, lineHeight:1.55,
                background:'#1a1815', color:'#e8e3d8',
                padding:'18px 22px', overflow:'auto', border:`1px solid ${HD_INK}`,
                margin:'14px 0', whiteSpace:'pre'}}>
    {lang && (<div style={{fontSize:9.5, letterSpacing:'0.2em', color:'#8a8275',
                            marginBottom:10, textTransform:'uppercase'}}>{lang}</div>)}
    <code>{children}</code>
  </pre>
);

Object.assign(window, {
  HD_PAPER, HD_PAPER2, HD_PAPER3, HD_EDGE, HD_EDGE2, HD_INK, HD_INK2, HD_INK3,
  HD_RULE, HD_GATE, HD_TRIP, HD_INFO,
  HD_F_DISP, HD_F_TEXT, HD_F_SER, HD_F_MONO,
  HdSection, HdEyebrow, HdStamp, HdBody, HdCaption, Mono,
  HdSpecTable, HdPanel, HdCode,
});
