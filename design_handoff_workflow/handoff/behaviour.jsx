// design_handoff_workflow/handoff/behaviour.jsx — interactions + edge cases
const HdBehaviour = () => (
  <HdSection id="behaviour" eyebrow="05 · Behaviour"
             title="What clicks do, what doesn't."
             sub={<>The map is mostly static — but two interactions earn their keep. The gate panel is the chart's progressive-disclosure mechanism; the workflow navigator is the page's primary control. Everything else is hover affordances and keyboard parity.</>}>

    <div style={{marginTop:24}}>
      <HdSpecTable rows={[
        ['gate badge · click',    <>Opens an inline panel anchored below the transition node, listing every validator and prompt-check on the route. Click again (or the panel's × button) to close. Only one panel open at a time. The panel is positioned in the document, not in the SVG, so it can extend beyond the SVG bounds.</>],
        ['gate panel content',    <>Header: mono <Mono>GATE · N CHECKS</Mono>. Body: rows, each with a 28px mono kind tag (<Mono>val</Mono> or <Mono>pmt</Mono>), the check name in mono 10.5px, and a 1-line italic-serif blurb in 11.5px ink-2. Rows separated by 1px dashed edge.</>],
        ['transition · hover',    <>Subtle border-weight increase from 1.6→2px and a 4% ink shadow-lift; 80ms ease-out. Cursor stays default — these are not links unless the team adds drill-through later.</>],
        ['workflow tile · click', <>Switches the active workflow. Page state replaces the entire chart; no transition animation in V1.</>],
        ['region · hover',        <>(post-V1) Highlights the region; dims the rest to 60% opacity. Drawer with the list of currently-active sessions in this status. Plumbing exists in the data layer; UI deferred.</>],
        ['port · click',          <>(post-V1) Sources open a drawer with the upstream connector definition; sinks open a drawer with downstream wiring. Mocks render statically.</>],
        ['keyboard',              <>Tab cycles through tiles in the navigator; arrow keys step through the active workflow's siblings. Esc closes the gate panel. No other shortcuts in V1.</>],
      ]}/>
    </div>

    <div style={{marginTop:36, display:'grid', gridTemplateColumns:'1fr 1fr', gap:24}}>
      <HdPanel title="Edge: empty controls" eyebrow="rule">
        Routes with zero validators and zero prompt-checks <strong>do not render a gate badge</strong>. Don't show <Mono>×0</Mono>. The transition node still appears with its label and actor stripe.
      </HdPanel>
      <HdPanel title="Edge: skill overflow" eyebrow="rule">
        Skill ribbons hard-cap at 3 lines, each truncated to 14 characters with an ellipsis. Long skill names like <Mono>backend-development</Mono> become <Mono>backend-deve…</Mono>. Hover surfaces the full list (post-V1 tooltip).
      </HdPanel>
      <HdPanel title="Edge: workflow with one status" eyebrow="rule">
        <Mono>project-maintenance</Mono> has 2 statuses with multiple side-routes between them. The layout function still places these on the north and south lanes; just visually denser. Don't special-case unless the engineering team finds a layout regression.
      </HdPanel>
      <HdPanel title="Edge: branched routes in lock mode" eyebrow="rule">
        If <Mono>gateMode='lock'</Mono> is ever toggled, both branched routes render as separate transition boxes side-by-side — no diamond. V1 ships <Mono>gateMode='diamond'</Mono> only; lock mode is preserved for an alternate-direction exploration on the canvas.
      </HdPanel>
    </div>
  </HdSection>
);

window.HdBehaviour = HdBehaviour;
