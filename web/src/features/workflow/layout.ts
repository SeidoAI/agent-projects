import type {
  WorkflowDefinition,
  WorkflowRoute,
  WorkflowStatus,
  WorkflowStatusArtifacts,
} from "@/lib/api/endpoints/workflow";
import { BRANCHES, type BranchOutcome } from "./decorations";

export const TX_W = 168;
export const TX_H = 50;
const REG_TOP = 110;
const REG_HEAD = 90;
const NORTH_LANE_DY = 75;
const SOUTH_LANE_DY = 80;
const PROOF_TOP_DY = 100;

export type GateMode = "lock" | "diamond";

export interface Point {
  x: number;
  y: number;
}

export interface LaidOutRegion {
  id: string;
  blurb: string;
  terminal: boolean;
  artifacts: WorkflowStatusArtifacts;
  rank: number;
  x: number;
  y: number;
  w: number;
  h: number;
  cx: number;
}

export interface LaidOutTransitionRoute {
  kind: "transition";
  id: string;
  route: WorkflowRoute;
  actor: string;
  label: string;
  command: string | null | undefined;
  cx: number;
  cy: number;
  w: number;
  h: number;
}

export interface LaidOutTransitionBranch {
  kind: "branch";
  id: string;
  command: string;
  actor: string;
  label: string;
  cx: number;
  cy: number;
  w: number;
  h: number;
}

export type LaidOutTransition = LaidOutTransitionRoute | LaidOutTransitionBranch;

export interface LaidOutEdge {
  id: string;
  route: WorkflowRoute;
  kind: string;
  actor: string;
  points: Point[];
  outcomeLabel?: string;
  isOut?: boolean;
  isIn?: boolean;
}

export interface LaidOutJit {
  id: string;
  label: string;
  status: string;
  x: number;
  y: number;
}

export interface LaidOutPort {
  id: string;
  kind: "source" | "sink";
  label: string;
  x: number;
  y: number;
}

export interface WorkflowLayout {
  width: number;
  height: number;
  regions: LaidOutRegion[];
  transitions: LaidOutTransition[];
  edges: LaidOutEdge[];
  jits: LaidOutJit[];
  ports: LaidOutPort[];
  mainY: number;
  northY: number;
  southY: number;
  proofTop: number;
  artifactRowY: number;
}

export interface LayoutOptions {
  width?: number;
  height?: number;
  gateMode?: GateMode;
  branches?: Record<string, BranchOutcome>;
}

const statusBlurb = (status: WorkflowStatus): string =>
  (status.description ?? status.label ?? "").trim();

const isTerminalStatus = (status: WorkflowStatus): boolean =>
  status.next?.kind === "terminal";

const yForKind = (
  kind: string,
  mainY: number,
  northY: number,
  southY: number,
): number => {
  switch (kind) {
    case "side":
    case "loop":
      return northY;
    case "return":
      return southY;
    default:
      return mainY;
  }
};

export function layoutWorkflow(
  wf: WorkflowDefinition,
  options: LayoutOptions = {},
): WorkflowLayout {
  const width = options.width ?? 1480;
  const height = options.height ?? 1100;
  const gateMode: GateMode = options.gateMode ?? "lock";
  const branches = options.branches ?? BRANCHES;

  // 1) regions
  const padX = 60;
  const N = wf.statuses.length;
  const regW = N > 0 ? (width - padX * 2) / N : 0;
  const regY = REG_TOP;
  const regH = height - REG_TOP - 60;
  const mainY = regY + REG_HEAD + 90;
  const northY = mainY - NORTH_LANE_DY;
  const southY = mainY + SOUTH_LANE_DY;
  const proofTop = mainY + PROOF_TOP_DY;

  const regions: LaidOutRegion[] = wf.statuses.map((s, i) => ({
    id: s.id,
    blurb: statusBlurb(s),
    terminal: isTerminalStatus(s),
    artifacts: s.artifacts,
    rank: i,
    x: padX + i * regW,
    y: regY,
    w: regW,
    h: regH,
    cx: padX + i * regW + regW / 2,
  }));
  const regById = new Map(regions.map((r) => [r.id, r]));

  // 2) classify routes — group branched routes
  const branchGroups = new Map<string, Array<{ route: WorkflowRoute; outcome: string }>>();
  wf.routes.forEach((r) => {
    const b = branches[r.id];
    if (!b) return;
    const list = branchGroups.get(b.branchOf) ?? [];
    list.push({ route: r, outcome: b.outcome });
    branchGroups.set(b.branchOf, list);
  });

  const transitions: LaidOutTransition[] = [];
  const edges: LaidOutEdge[] = [];
  const diamondById = new Map<string, LaidOutTransitionBranch>();

  // 3) Branch diamonds (V2 mode)
  if (gateMode === "diamond") {
    branchGroups.forEach((outcomes, commandKey) => {
      const first = outcomes[0];
      if (!first) return;
      const fromR = regById.get(first.route.from);
      if (!fromR) return;
      const dnode: LaidOutTransitionBranch = {
        kind: "branch",
        id: `branch-${commandKey}`,
        command: commandKey,
        actor: first.route.actor,
        label: commandKey,
        cx: fromR.x + fromR.w - 8,
        cy: mainY,
        w: 110,
        h: 64,
      };
      transitions.push(dnode);
      diamondById.set(commandKey, dnode);
    });
  }

  // 4) For each route, place the transition node + edges
  wf.routes.forEach((r) => {
    const fromR = regById.get(r.from);
    const toR = regById.get(r.to);
    const sourceFrom = r.from.startsWith("source:");
    const sinkTo = r.to.startsWith("sink:");

    const fromAnchorX = sourceFrom ? padX - 22 : (fromR?.cx ?? padX);
    const toAnchorX = sinkTo ? width - padX + 22 : (toR?.cx ?? width - padX);
    const fromAnchorY = mainY;
    const toAnchorY = mainY;
    const txY = yForKind(r.kind, mainY, northY, southY);

    const branchInfo = branches[r.id];
    const isBranchOutcome = gateMode === "diamond" && Boolean(branchInfo);
    const dnode =
      isBranchOutcome && branchInfo
        ? (diamondById.get(branchInfo.branchOf) ?? null)
        : null;

    let txX: number;
    if (r.kind === "forward" || r.kind === "terminal") {
      if (sourceFrom && toR) txX = toR.x - 4;
      else if (sinkTo && fromR) txX = fromR.x + fromR.w + 4;
      else if (fromR && toR) txX = (fromR.x + fromR.w + toR.x) / 2;
      else txX = (fromAnchorX + toAnchorX) / 2;
    } else if (fromR && toR) {
      txX = (fromR.cx + toR.cx) / 2;
    } else {
      txX = (fromAnchorX + toAnchorX) / 2;
    }

    if (isBranchOutcome && dnode && toR) {
      txX = (dnode.cx + 60 + toR.cx) / 2;
    }

    transitions.push({
      kind: "transition",
      id: `t-${r.id}`,
      route: r,
      actor: r.actor,
      label: r.label,
      command: r.command,
      cx: txX,
      cy: txY,
      w: TX_W,
      h: TX_H,
    });

    if (isBranchOutcome && dnode && branchInfo) {
      const a: Point = { x: dnode.cx + 60, y: dnode.cy };
      const b: Point = { x: txX - TX_W / 2 - 4, y: txY };
      edges.push({
        id: `e-bin-${r.id}`,
        route: r,
        kind: r.kind,
        actor: r.actor,
        points: orthogonal(a, b),
        outcomeLabel: branchInfo.outcome,
        isOut: false,
      });
      const c: Point = { x: txX + TX_W / 2 + 4, y: txY };
      const d: Point = { x: toAnchorX, y: mainY };
      edges.push({
        id: `e-bout-${r.id}`,
        route: r,
        kind: r.kind,
        actor: r.actor,
        points: orthogonal(c, d, {
          detour: r.kind === "return" ? southY + 30 : null,
        }),
        isOut: true,
      });
    } else {
      const a: Point = { x: fromAnchorX, y: fromAnchorY };
      const b: Point = { x: txX - TX_W / 2 - 4, y: txY };
      const c: Point = { x: txX + TX_W / 2 + 4, y: txY };
      const d: Point = { x: toAnchorX, y: toAnchorY };
      const isDetour = r.kind === "return" || r.kind === "side" || r.kind === "loop";

      edges.push({
        id: `e-in-${r.id}`,
        route: r,
        kind: r.kind,
        actor: r.actor,
        points: isDetour ? [a, { x: a.x, y: txY }, b] : orthogonal(a, b),
        isIn: true,
      });
      edges.push({
        id: `e-out-${r.id}`,
        route: r,
        kind: r.kind,
        actor: r.actor,
        points: isDetour ? [c, { x: d.x, y: txY }, d] : orthogonal(c, d),
        isOut: true,
      });
    }
  });

  // 5) JITs in 1-column vertical list per region (anchored to status.jit_prompts)
  const jits: LaidOutJit[] = [];
  const JIT_W = 28;
  const stepY = JIT_W + 22;
  wf.statuses.forEach((s) => {
    const reg = regById.get(s.id);
    if (!reg) return;
    s.jit_prompts.forEach((jitId, k) => {
      jits.push({
        id: `${s.id}-${jitId}`,
        label: jitId,
        status: s.id,
        x: reg.cx,
        y: proofTop + 26 + k * stepY,
      });
    });
  });

  // 6) Artifact row Y (renderer places tiles)
  const artifactRowY = regY + regH - 36;

  // 7) Sources / sinks
  const ports: LaidOutPort[] = [];
  const seen = new Set<string>();
  wf.routes.forEach((r) => {
    if (r.from.startsWith("source:") && !seen.has(r.from)) {
      ports.push({
        id: r.from,
        kind: "source",
        label: r.from.replace("source:", ""),
        x: padX - 28,
        y: mainY,
      });
      seen.add(r.from);
    }
    if (r.to.startsWith("sink:") && !seen.has(r.to)) {
      ports.push({
        id: r.to,
        kind: "sink",
        label: r.to.replace("sink:", ""),
        x: width - padX + 28,
        y: mainY,
      });
      seen.add(r.to);
    }
  });

  return {
    width,
    height,
    regions,
    transitions,
    edges,
    jits,
    ports,
    mainY,
    northY,
    southY,
    proofTop,
    artifactRowY,
  };
}

interface OrthogonalOpts {
  detour?: number | null;
}

export function orthogonal(a: Point, b: Point, opts: OrthogonalOpts = {}): Point[] {
  const detour = opts.detour ?? null;
  if (Math.abs(a.y - b.y) < 1 && detour == null) return [a, b];
  if (detour != null) {
    return [a, { x: a.x, y: detour }, { x: b.x, y: detour }, b];
  }
  const mx = (a.x + b.x) / 2;
  return [a, { x: mx, y: a.y }, { x: mx, y: b.y }, b];
}

export function pathFromPoints(pts: Point[], r = 10): string {
  const head = pts[0];
  if (!head || pts.length < 2) return "";
  const second = pts[1];
  if (pts.length === 2 && second) {
    return `M ${head.x} ${head.y} L ${second.x} ${second.y}`;
  }
  let d = `M ${head.x} ${head.y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const prev = pts[i - 1];
    const cur = pts[i];
    const nxt = pts[i + 1];
    if (!prev || !cur || !nxt) continue;
    const inDx = Math.sign(cur.x - prev.x);
    const inDy = Math.sign(cur.y - prev.y);
    const outDx = Math.sign(nxt.x - cur.x);
    const outDy = Math.sign(nxt.y - cur.y);
    const distIn = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const distOut = Math.hypot(nxt.x - cur.x, nxt.y - cur.y);
    const rr = Math.min(r, distIn / 2, distOut / 2);
    const before = { x: cur.x - inDx * rr, y: cur.y - inDy * rr };
    const after = { x: cur.x + outDx * rr, y: cur.y + outDy * rr };
    d += ` L ${before.x} ${before.y} Q ${cur.x} ${cur.y}, ${after.x} ${after.y}`;
  }
  const last = pts[pts.length - 1];
  if (last) d += ` L ${last.x} ${last.y}`;
  return d;
}
