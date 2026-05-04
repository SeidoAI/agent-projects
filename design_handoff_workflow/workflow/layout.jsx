// workflow/layout.jsx — proper lane allocation for traditional flowchart.
//
// Lanes (top→bottom inside a region band):
//   NORTH (sides + loops):  detour transitions ride above main line
//   MAIN:                    forward transitions sit on the boundary
//   SOUTH-RETURNS:           returns ride below main, dashed
//   PROOF SHELF (per region):
//     - JIT prompts: 2D grid of badges
//     - Artifacts:   tile row at the very bottom
//
// Branched outcomes (V2): each outcome route gets its own y-lane (forward main
// or return south); a real diamond at the *origin region's east edge* sources
// both edges, with named outcome labels on the outgoing edges.

const TX_W = 168;
const TX_H = 50;
const REG_TOP = 110;
const REG_HEAD = 90;     // status header height (label + blurb)
const NORTH_LANE_DY = 75;
const SOUTH_LANE_DY = 80;
const PROOF_TOP_DY = 100;  // distance below main line where proof shelf starts
const JIT_W = 28;
const JIT_GAP_X = 38;
const JIT_GAP_Y = 22;

const layoutWorkflow = (wf, options = {}) => {
  const { width = 1480, height = 1100, gateMode = 'lock' } = options;

  // 1) regions
  const padX = 60;
  const N = wf.statuses.length;
  const regW = (width - padX*2) / N;
  const regY = REG_TOP;
  const regH = height - REG_TOP - 60;
  const mainY = regY + REG_HEAD + 90;   // y of forward main line
  const northY = mainY - NORTH_LANE_DY;
  const southY = mainY + SOUTH_LANE_DY;
  const proofTop = mainY + PROOF_TOP_DY;

  const regions = wf.statuses.map((s, i) => ({
    id: s.id, blurb: s.blurb, terminal: !!s.terminal,
    artifacts: s.artifacts,
    x: padX + i*regW, y: regY, w: regW, h: regH,
    cx: padX + i*regW + regW/2,
    rank: i, pressure: 0,
  }));
  const regById = Object.fromEntries(regions.map(r => [r.id, r]));

  // 2) classify routes — group branched routes
  const branchGroups = {};
  wf.routes.forEach(r => {
    const b = window.BRANCHES?.[r.id];
    if (b) (branchGroups[b.branchOf] ||= []).push({ route:r, outcome: b.outcome });
  });
  const branchedIds = new Set(Object.values(branchGroups).flat().map(x=>x.route.id));

  const transitions = [];
  const edges = [];

  // Helper: choose Y for a route by kind
  const yForKind = (kind) =>
    kind === 'side'   ? northY :
    kind === 'return' ? southY :
    kind === 'loop'   ? northY :
    mainY;

  // 3) Branch diamonds (V2 mode)
  const diamondById = {};
  if (gateMode === 'diamond') {
    Object.entries(branchGroups).forEach(([commandKey, outcomes]) => {
      const from = outcomes[0].route.from;
      const fromR = regById[from];
      if (!fromR) return;
      const dx = fromR.x + fromR.w - 8;
      const dy = mainY;
      const did = `branch-${commandKey}`;
      const dnode = {
        id: did, kind:'branch', command: commandKey,
        actor: outcomes[0].route.actor, label: commandKey,
        cx: dx, cy: dy, w: 110, h: 64,
      };
      transitions.push(dnode);
      diamondById[commandKey] = dnode;
    });
  }

  // 4) For each route, place the transition node + edges
  wf.routes.forEach((r) => {
    const fromR = regById[r.from];
    const toR   = regById[r.to];
    const sourceFrom = r.from.startsWith('source:');
    const sinkTo     = r.to.startsWith('sink:');

    const fromAnchorX = sourceFrom ? padX - 22 : (fromR ? fromR.cx : padX);
    const toAnchorX   = sinkTo     ? width - padX + 22 : (toR ? toR.cx : width - padX);
    const fromAnchorY = mainY;
    const toAnchorY   = mainY;
    const txY = yForKind(r.kind);

    // If V2 and this is a branched outcome, anchor edge from the diamond
    // and don't place an in-edge. Place the transition box at txY in the
    // appropriate lane.
    const branchInfo = window.BRANCHES?.[r.id];
    const isBranchOutcome = gateMode === 'diamond' && branchInfo;
    const dnode = isBranchOutcome ? diamondById[branchInfo.branchOf] : null;

    // Transition node x: sits at boundary for forward; midway in detour lane otherwise.
    let txX;
    if (r.kind === 'forward' || r.kind === 'terminal') {
      if (sourceFrom && toR) txX = toR.x - 4;
      else if (sinkTo && fromR) txX = fromR.x + fromR.w + 4;
      else if (fromR && toR) txX = (fromR.x + fromR.w + toR.x) / 2;
      else txX = (fromAnchorX + toAnchorX) / 2;
    } else {
      // detour: position over the *destination* region for clarity, with offset
      // for loops/returns where from===to-1 or to===from
      if (fromR && toR) {
        // midway between region centers
        txX = (fromR.cx + toR.cx) / 2;
      } else {
        txX = (fromAnchorX + toAnchorX) / 2;
      }
    }

    // For branched outcomes in V2, push the transition box along the outcome lane
    // so it doesn't overlap the diamond.
    if (isBranchOutcome) {
      const isReturnOutcome = r.kind === 'return';
      // Place outcome tx box well past the diamond, halfway to its destination
      if (toR) {
        txX = (dnode.cx + 60 + toR.cx) / 2;
      }
    }

    const txId = `t-${r.id}`;
    transitions.push({
      id: txId, kind:'transition', route: r,
      actor: r.actor, label: r.label, command: r.command,
      cx: txX, cy: txY, w: TX_W, h: TX_H,
    });

    // pressure calc
    const cv = (r.controls.validators.length||0) +
               (r.controls.prompt_checks.length||0)*0.7;
    if (toR) toR.pressure += cv;

    // edges
    if (isBranchOutcome) {
      // diamond-out → tx-in (curved/orthogonal)
      const a = { x: dnode.cx + 60, y: dnode.cy };
      const b = { x: txX - TX_W/2 - 4, y: txY };
      edges.push({
        id:`e-bin-${r.id}`, route:r, kind:r.kind, actor:r.actor, points: orthogonal(a,b),
        outcomeLabel: branchInfo.outcome, isOut: false,
      });
      // tx-out → toR.cx (return goes back to fromR for loop visualization, but
      // fromR was its own from. Instead route to the actual destination.)
      const c = { x: txX + TX_W/2 + 4, y: txY };
      const d = { x: toAnchorX, y: r.kind==='return' ? mainY : mainY };
      edges.push({
        id:`e-bout-${r.id}`, route:r, kind:r.kind, actor:r.actor,
        points: orthogonal(c, d, { detour: r.kind==='return' ? southY+30 : null }),
        isOut: true,
      });
    } else {
      const a = { x: fromAnchorX, y: fromAnchorY };
      const b = { x: txX - TX_W/2 - 4, y: txY };
      const c = { x: txX + TX_W/2 + 4, y: txY };
      const d = { x: toAnchorX, y: toAnchorY };

      // For non-forward routes (return/side/loop) we drop down/up to the
      // detour lane explicitly: from-main → bend → detour-lane (tx) → bend → to-main.
      const isDetour = r.kind === 'return' || r.kind === 'side' || r.kind === 'loop';

      edges.push({
        id:`e-in-${r.id}`, route:r, kind:r.kind, actor:r.actor,
        points: isDetour
          ? [a, {x:a.x, y:txY}, b]   // drop straight down/up first, then over
          : orthogonal(a, b),
        isIn: true,
      });
      edges.push({
        id:`e-out-${r.id}`, route:r, kind:r.kind, actor:r.actor,
        points: isDetour
          ? [c, {x:d.x, y:txY}, d]   // over, then straight up/down to to-main
          : orthogonal(c, d),
        isOut: true,
      });
    }
  });

  // 5) JITs in 1-column vertical list in proof shelf (per region)
  const jits = [];
  const jitsByStatus = {};
  (window.JIT_ANCHORS || []).filter(j => j.workflow === wf.id).forEach(j => {
    (jitsByStatus[j.status] ||= []).push(j);
  });
  Object.entries(jitsByStatus).forEach(([statusId, list]) => {
    const reg = regById[statusId];
    if (!reg) return;
    const startY = proofTop + 26;
    const stepY = JIT_W + 22; // stacked vertically with label below
    list.forEach((j, k) => {
      jits.push({
        id: j.id, label: j.id, status: statusId,
        x: reg.cx,
        y: startY + k*stepY,
      });
    });
  });

  // 6) Artifacts placed at very bottom of region (one row per region)
  // (renderer will place them itself; we just expose the row Y here)
  const artifactRowY = regY + regH - 36;

  // 7) Sources/Sinks
  const ports = [];
  const seen = new Set();
  wf.routes.forEach(r => {
    if (r.from.startsWith('source:') && !seen.has(r.from)) {
      ports.push({ id:r.from, kind:'source', label:r.from.replace('source:',''),
                   x: padX - 28, y: mainY });
      seen.add(r.from);
    }
    if (r.to.startsWith('sink:') && !seen.has(r.to)) {
      ports.push({ id:r.to, kind:'sink', label:r.to.replace('sink:',''),
                   x: width - padX + 28, y: mainY });
      seen.add(r.to);
    }
  });

  return {
    width, height, regions, transitions, edges, jits, ports,
    mainY, northY, southY, proofTop, artifactRowY,
  };
};

// Orthogonal path between a → b. Bends at midpoint, optionally with a detour Y.
const orthogonal = (a, b, opts={}) => {
  const { detour = null } = opts;
  if (Math.abs(a.y - b.y) < 1 && detour == null) return [a, b];
  const mx = (a.x + b.x) / 2;
  if (detour != null) {
    return [a, {x:a.x, y:detour}, {x:b.x, y:detour}, b];
  }
  return [a, {x:mx, y:a.y}, {x:mx, y:b.y}, b];
};

const pathFromPoints = (pts, r=10) => {
  if (pts.length < 2) return '';
  if (pts.length === 2) return `M ${pts[0].x} ${pts[0].y} L ${pts[1].x} ${pts[1].y}`;
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i=1; i<pts.length-1; i++) {
    const prev = pts[i-1], cur = pts[i], nxt = pts[i+1];
    const inDx = Math.sign(cur.x - prev.x), inDy = Math.sign(cur.y - prev.y);
    const outDx = Math.sign(nxt.x - cur.x), outDy = Math.sign(nxt.y - cur.y);
    const distIn = Math.hypot(cur.x-prev.x, cur.y-prev.y);
    const distOut = Math.hypot(nxt.x-cur.x, nxt.y-cur.y);
    const rr = Math.min(r, distIn/2, distOut/2);
    const before = { x: cur.x - inDx*rr, y: cur.y - inDy*rr };
    const after  = { x: cur.x + outDx*rr, y: cur.y + outDy*rr };
    d += ` L ${before.x} ${before.y} Q ${cur.x} ${cur.y}, ${after.x} ${after.y}`;
  }
  const last = pts[pts.length-1];
  d += ` L ${last.x} ${last.y}`;
  return d;
};

Object.assign(window, { layoutWorkflow, pathFromPoints, TX_W, TX_H });
