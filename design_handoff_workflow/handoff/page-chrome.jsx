// design_handoff_workflow/handoff/page-chrome.jsx — header, navigator, legend
const HdPageChrome = () => (
  <HdSection id="page-chrome" eyebrow="04 · Page chrome"
             title="Header, navigator, legend."
             sub={<>Outside the chart, the page wears three pieces of furniture: a workflow-family navigator on top, the page header (title + version stamps), and a horizontal legend strip. All three live above the SVG; the SVG itself contains its own compass labels.</>}>

    <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:32, marginTop:24}}>
      <HdPanel title="Family navigator" eyebrow="component">
        <p style={{margin:'0 0 12px'}}>A horizontal rail grouped by workflow family — coding / pm / maintenance. Active workflow gets ink fill + paper text; inactive sit on paper-2 with edge border. Each tile shows the workflow's primary actor as a coloured dot, the label, and a mono caption with status + route counts.</p>
        <ul style={{margin:'0 0 0 18px', padding:0, fontSize:13.5, lineHeight:1.55}}>
          <li>Family heading: mono 9.5px, tracked 0.18em, ink-3.</li>
          <li>Tile size: min-width 160px, padding 8×10, gap 6 between tiles.</li>
          <li>Tile typography: Bricolage 12.5/500 for label; mono 9.5px for the count caption.</li>
          <li>Family separator: 1px dashed edge between family columns.</li>
        </ul>
      </HdPanel>

      <HdPanel title="Page header" eyebrow="component">
        <p style={{margin:'0 0 12px'}}>Two-row title cluster on the left (eyebrow + sans title + italic-serif blurb) and a meta cluster on the right (mono version line + two stamps).</p>
        <ul style={{margin:'0 0 0 18px', padding:0, fontSize:13.5, lineHeight:1.55}}>
          <li>Eyebrow: <Mono>workflow · {`<wf.id>`}</Mono>, mono 11/0.18em, ink-3.</li>
          <li>Title: Bricolage 34/600, ink, letter-spacing −0.025em.</li>
          <li>Blurb: Instrument Serif 15/italic, ink-2, max-width 780px.</li>
          <li>Right cluster: <Mono>workflow.yaml · v0.9.6 · gate-as-diamond</Mono>, two stamps (<HdStamp tone="rule">DEFINITION</HdStamp>{' '}<HdStamp tone="mute">6 ST · 8 RT</HdStamp>).</li>
        </ul>
      </HdPanel>

      <HdPanel title="Inline legend" eyebrow="component">
        <p style={{margin:'0 0 12px'}}>A single horizontal strip below the header, sitting on paper-2 with a 1px edge border. Three groups: <em>actors</em> (coloured strokes), <em>routes</em> (line styles), <em>markers</em> (gate / JIT glyphs).</p>
        <ul style={{margin:'0 0 0 18px', padding:0, fontSize:13.5, lineHeight:1.55}}>
          <li>Padding 8×12; gap 14 between items; mono 10px ink-2.</li>
          <li>Actor swatch: 18×3 coloured rect, no stroke.</li>
          <li>Route swatch: 36×10 svg with stroke pattern.</li>
          <li>Marker swatch: 14×14 svg with the literal glyph (gate lock or JIT badge).</li>
        </ul>
      </HdPanel>

      <HdPanel title="In-SVG compass" eyebrow="component">
        <p style={{margin:'0 0 12px'}}>The four directional labels (WEST · INTENT, NORTH · CONTROL, EAST · CLOSURE, SOUTH · PROOF) are rendered <em>inside the SVG</em>, not in the page chrome — they are part of the chart, not the page.</p>
        <ul style={{margin:'0 0 0 18px', padding:0, fontSize:13.5, lineHeight:1.55}}>
          <li>Mono 9.5px, tracked 0.18em, ink-3.</li>
          <li>WEST anchored at <Mono>(40, 28)</Mono>, EAST at <Mono>(width − 40, 28)</Mono> right-aligned.</li>
          <li>NORTH centred at <Mono>(width/2, 28)</Mono>; SOUTH centred at <Mono>(width/2, height − 12)</Mono>.</li>
        </ul>
      </HdPanel>
    </div>
  </HdSection>
);

window.HdPageChrome = HdPageChrome;
