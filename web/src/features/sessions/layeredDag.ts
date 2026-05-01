/**
 * Horizontal layered DAG with orthogonal (Manhattan) routing for the
 * sessions flow view.
 *
 * Pipeline:
 *   1. Layer assignment via longest-path from sources (cycle-safe by
 *      capping iterations to N).
 *   2. Sugiyama dummy insertion: any edge that spans more than one layer
 *      is replaced by a chain of segments through invisible dummy nodes
 *      on each intermediate layer. Dummies participate in the in-layer
 *      sort so the routing avoids real-node rows.
 *   3. Status-biased barycenter ordering: standard barycenter to minimise
 *      crossings, with a small additive bias (`statusOrderOf * 0.2`) so
 *      executing rows float to the top of each layer when ties allow.
 *   4. Per-corridor lane allocation: for each gap between adjacent layers,
 *      allocate one vertical lane x per *unique source*. Edges from the
 *      same source share the outgoing horizontal stub — that's the
 *      "stream" effect.
 *   5. Each logical edge becomes a single right-angle polyline through
 *      its dummies. {@link roundedOrthogonalPath} renders that polyline
 *      with quadratic-Bézier corner fillets.
 */

export interface DagInput {
  nodes: { id: string }[];
  /** "source must finish before target" — i.e. blocker → blocked. */
  edges: { source: string; target: string }[];
  /** Optional status priority (lower = higher up). Used for tie-break. */
  statusOrderOf?: (id: string) => number;
}

export interface DagEdgeRoute {
  source: string;
  target: string;
  /** Right-angle polyline; orthogonal segments meet at right angles. */
  points: { x: number; y: number }[];
}

export interface DagLayout {
  positions: Record<string, { x: number; y: number }>;
  width: number;
  height: number;
  edges: DagEdgeRoute[];
}

export interface LayoutOptions {
  layerStride?: number;
  rowStride?: number;
  nodeWidth?: number;
  nodeHeight?: number;
  paddingX?: number;
  paddingY?: number;
}

const DEFAULTS: Required<LayoutOptions> = {
  layerStride: 260,
  rowStride: 76,
  nodeWidth: 168,
  nodeHeight: 48,
  paddingX: 40,
  paddingY: 40,
};

interface ChainEdge {
  source: string;
  target: string;
  /** Intermediate dummy ids in source→target order; empty for adjacent layers. */
  dummies: string[];
}

interface LayoutNode {
  id: string;
  kind: "real" | "dummy";
  /** For dummies: the index of the owning logical edge in `chained`. */
  edgeIndex?: number;
}

export function layoutLayeredDag(input: DagInput, opts: LayoutOptions = {}): DagLayout {
  const o = { ...DEFAULTS, ...opts };
  const ids = input.nodes.map((n) => n.id);
  const idSet = new Set(ids);
  const rawEdges = input.edges.filter(
    (e) => idSet.has(e.source) && idSet.has(e.target) && e.source !== e.target,
  );

  // ---------------- 1. Layer assignment ---------------------------------
  const layer = new Map<string, number>();
  for (const id of ids) layer.set(id, 0);
  for (let pass = 0; pass < ids.length; pass += 1) {
    let changed = false;
    for (const e of rawEdges) {
      const ls = layer.get(e.source) ?? 0;
      const lt = layer.get(e.target) ?? 0;
      if (lt < ls + 1) {
        layer.set(e.target, ls + 1);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const numLayers = ids.length === 0 ? 0 : (Math.max(0, ...layer.values()) + 1);
  const layers: LayoutNode[][] = Array.from({ length: numLayers }, () => []);
  for (const id of ids) layers[layer.get(id) ?? 0]!.push({ id, kind: "real" });

  // ---------------- 2. Dummy insertion for skip-layer edges -------------
  const chained: ChainEdge[] = [];
  // Adjacency at the *segment* level — used by the barycenter sweep.
  const segOut = new Map<string, string[]>();
  const segIn = new Map<string, string[]>();
  const ensure = (m: Map<string, string[]>, k: string) => {
    let a = m.get(k);
    if (!a) {
      a = [];
      m.set(k, a);
    }
    return a;
  };
  // For dummies: which logical edge owns them (carries source's status).
  const dummyOwner = new Map<string, number>();

  rawEdges.forEach((e, idx) => {
    const ls = layer.get(e.source)!;
    const lt = layer.get(e.target)!;
    if (lt - ls <= 1) {
      ensure(segOut, e.source).push(e.target);
      ensure(segIn, e.target).push(e.source);
      chained.push({ source: e.source, target: e.target, dummies: [] });
      return;
    }
    const dummies: string[] = [];
    let prev = e.source;
    for (let li = ls + 1; li < lt; li += 1) {
      const dId = `__dummy__${idx}__${li}`;
      dummies.push(dId);
      layers[li]!.push({ id: dId, kind: "dummy", edgeIndex: idx });
      layer.set(dId, li);
      dummyOwner.set(dId, idx);
      ensure(segOut, prev).push(dId);
      ensure(segIn, dId).push(prev);
      prev = dId;
    }
    ensure(segOut, prev).push(e.target);
    ensure(segIn, e.target).push(prev);
    chained.push({ source: e.source, target: e.target, dummies });
  });

  // ---------------- 3. Status-biased barycenter -------------------------
  const order = new Map<string, number>();
  for (const lyr of layers) lyr.forEach((n, i) => order.set(n.id, i));

  // Status used for the bias: real nodes use their own status; dummies
  // inherit the source status of the edge they belong to.
  const statusOrderOf = input.statusOrderOf ?? (() => 0);
  const nodeStatusOrder = (id: string): number => {
    const ownerIdx = dummyOwner.get(id);
    if (ownerIdx !== undefined) {
      const owner = chained[ownerIdx]!;
      return statusOrderOf(owner.source);
    }
    return statusOrderOf(id);
  };
  const STATUS_BIAS = 0.2;

  const sweep = (downward: boolean) => {
    const range = downward
      ? [...layers.keys()].slice(1)
      : [...layers.keys()].slice(0, -1).reverse();
    for (const li of range) {
      const lyr = layers[li]!;
      const bc = new Map<string, number>();
      for (const n of lyr) {
        const ns = (downward ? segIn.get(n.id) : segOut.get(n.id)) ?? [];
        const baseline =
          ns.length === 0
            ? (order.get(n.id) ?? 0)
            : ns.reduce((s, m) => s + (order.get(m) ?? 0), 0) / ns.length;
        bc.set(n.id, baseline + STATUS_BIAS * nodeStatusOrder(n.id));
      }
      lyr.sort((a, b) => (bc.get(a.id) ?? 0) - (bc.get(b.id) ?? 0));
      lyr.forEach((n, i) => order.set(n.id, i));
    }
  };
  // Four alternating sweeps converge well for the small graphs we see here.
  sweep(true);
  sweep(false);
  sweep(true);
  sweep(false);

  // ---------------- 4. Coordinates --------------------------------------
  const widest = layers.reduce((m, l) => Math.max(m, l.length), 0);
  const colHeight = widest * o.rowStride;

  const yOf = new Map<string, number>();
  layers.forEach((lyr) => {
    const span = lyr.length * o.rowStride;
    const startY = o.paddingY + (colHeight - span) / 2 + o.nodeHeight / 2;
    lyr.forEach((n, i) => yOf.set(n.id, startY + i * o.rowStride));
  });

  const xForLayer = (li: number) => o.paddingX + li * o.layerStride + o.nodeWidth / 2;
  const halfWidthOf = (id: string): number => (dummyOwner.has(id) ? 0 : o.nodeWidth / 2);

  const positions: Record<string, { x: number; y: number }> = {};
  for (const id of ids) {
    positions[id] = { x: xForLayer(layer.get(id)!), y: yOf.get(id) ?? 0 };
  }

  // ---------------- 5. Per-corridor lane allocation ---------------------
  // For corridor `ci` (between layers ci and ci+1), find unique sources of
  // segments crossing that corridor. Sort by source y. Allocate a lane x
  // per source, evenly spaced inside the corridor.
  const laneFor = new Map<string, number>(); // key: `${corridor}::${source}` → lane x
  const corridorLeft = (ci: number) => xForLayer(ci) + o.nodeWidth / 2;
  const corridorRight = (ci: number) => xForLayer(ci + 1) - o.nodeWidth / 2;

  // Build segments-per-corridor view by walking each chain.
  const sourcesByCorridor: Map<number, Map<string, number>> = new Map();
  // value is source y; we sort by it later
  const recordSegment = (ci: number, sourceId: string, sourceY: number) => {
    if (!sourcesByCorridor.has(ci)) sourcesByCorridor.set(ci, new Map());
    const m = sourcesByCorridor.get(ci)!;
    if (!m.has(sourceId)) m.set(sourceId, sourceY);
  };

  chained.forEach((ce) => {
    let cur = ce.source;
    let ci = layer.get(cur)!;
    for (const d of ce.dummies) {
      recordSegment(ci, cur, yOf.get(cur) ?? 0);
      cur = d;
      ci += 1;
    }
    recordSegment(ci, cur, yOf.get(cur) ?? 0);
  });

  for (const [ci, sources] of sourcesByCorridor) {
    const sorted = [...sources.entries()].sort((a, b) => a[1] - b[1]);
    const left = corridorLeft(ci);
    const right = corridorRight(ci);
    const span = right - left;
    const n = sorted.length;
    sorted.forEach(([id], i) => {
      const x = left + ((i + 1) * span) / (n + 1);
      laneFor.set(`${ci}::${id}`, x);
    });
  }

  // ---------------- 6. Build edge polylines ----------------------------
  const dagEdges: DagEdgeRoute[] = chained.map((ce) => {
    const points: { x: number; y: number }[] = [];
    const sPos = positions[ce.source]!;
    points.push({ x: sPos.x + halfWidthOf(ce.source), y: sPos.y });

    const chain = [...ce.dummies, ce.target];
    let cur = ce.source;
    let ci = layer.get(cur)!;
    for (const next of chain) {
      const lane = laneFor.get(`${ci}::${cur}`)!;
      const curY = yOf.get(cur) ?? 0;
      const nextPos =
        next === ce.target
          ? positions[next]!
          : { x: xForLayer(ci + 1), y: yOf.get(next) ?? 0 };
      const nextY = nextPos.y;
      points.push({ x: lane, y: curY });
      points.push({ x: lane, y: nextY });
      points.push({ x: nextPos.x - halfWidthOf(next), y: nextY });
      cur = next;
      ci += 1;
    }
    return { source: ce.source, target: ce.target, points };
  });

  const width = numLayers * o.layerStride + o.paddingX * 2;
  const height = colHeight + o.paddingY * 2;
  return { positions, width, height, edges: dagEdges };
}

/**
 * Render a right-angle polyline as an SVG path string with rounded
 * corners. Each interior vertex becomes a quadratic-Bézier fillet of
 * radius `r`, clamped to half the shorter incident segment so paths
 * with short legs don't overshoot.
 */
export function roundedOrthogonalPath(
  points: { x: number; y: number }[],
  radius = 8,
): string {
  if (points.length === 0) return "";
  const first = points[0]!;
  if (points.length === 1) {
    return `M ${first.x.toFixed(2)} ${first.y.toFixed(2)}`;
  }
  let d = `M ${first.x.toFixed(2)} ${first.y.toFixed(2)}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const prev = points[i - 1]!;
    const curr = points[i]!;
    const next = points[i + 1]!;
    const inLen = Math.hypot(curr.x - prev.x, curr.y - prev.y);
    const outLen = Math.hypot(next.x - curr.x, next.y - curr.y);
    if (inLen === 0 || outLen === 0) continue;
    const inDx = (curr.x - prev.x) / inLen;
    const inDy = (curr.y - prev.y) / inLen;
    const outDx = (next.x - curr.x) / outLen;
    const outDy = (next.y - curr.y) / outLen;
    // Colinear: no corner, just draw through.
    if (Math.abs(inDx - outDx) < 1e-6 && Math.abs(inDy - outDy) < 1e-6) {
      d += ` L ${curr.x.toFixed(2)} ${curr.y.toFixed(2)}`;
      continue;
    }
    const r = Math.min(radius, inLen / 2, outLen / 2);
    const preX = curr.x - inDx * r;
    const preY = curr.y - inDy * r;
    const postX = curr.x + outDx * r;
    const postY = curr.y + outDy * r;
    d += ` L ${preX.toFixed(2)} ${preY.toFixed(2)}`;
    d += ` Q ${curr.x.toFixed(2)} ${curr.y.toFixed(2)} ${postX.toFixed(2)} ${postY.toFixed(2)}`;
  }
  const last = points[points.length - 1]!;
  d += ` L ${last.x.toFixed(2)} ${last.y.toFixed(2)}`;
  return d;
}
