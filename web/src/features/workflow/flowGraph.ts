import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type {
  WorkflowArtifactRef,
  WorkflowDefinition,
  WorkflowGraph,
  WorkflowRoute,
  WorkflowStatus,
  WorkflowWorkStep,
} from "@/lib/api/endpoints/workflow";
import { BRANCHES, type BranchOutcome } from "./decorations";
import { ACTOR_COLOR, isKnownActor } from "./tokens";

const actorStrokeColor = (actor: string): string =>
  isKnownActor(actor) ? ACTOR_COLOR[actor] : "var(--color-ink)";

// ── visual constants ──────────────────────────────────────────────
export const REGION_H = 760;
export const REGION_PAD_TOP = 16;
export const REGION_PAD_X = 22;
export const HEADER_H = 92;
export const INPUTS_BAND_H = 64;
export const OUTPUTS_BAND_H = 64;
export const REGION_PAD_BOTTOM = 24;

export const WORK_W = 220;
export const WORK_H = 72;

export const TX_W = 200;
// Same height as WORK_H so the gate/transition boxes' tops align with
// the work-step boxes' tops. Both centre at Y_WORK so handles align too;
// matching heights makes that alignment *look* clean (the eye reads box
// tops, not centres — a 12px height diff reads as a 6px sunken row).
export const TX_H = 72;

export const CHIP_H = 26;
export const CHIP_GAP = 14;
export const CHIP_PAD_X = 14;
export const SKILL_CHIP_W_PER_CHAR = 7;
export const REF_CHIP_MIN_W = 78;

export const TILE_W = 200;
export const TILE_H = 38;
// Reserved corner-fold width on the tile; label area must stop short of this.
export const TILE_FOLD = 16;
// Inner padding on all sides of the label area (left of icon, between icon
// and text, right of text up to the fold). Keeps long labels from kissing
// the icon or running under the fold.
export const TILE_PAD_L = 12;
export const TILE_PAD_RIGHT = 14;
export const TILE_ICON_GAP = 8;

export const JIT_W = 28;
export const JIT_GAP = 8;

// Spacing rule: every edge must have a visible segment ≥ MIN_EDGE_LEN.
// Region widths are chosen so the work_step (centred) is at least
// MIN_EDGE_LEN from each adjacent boundary transition (centred on the wall).
// region_w ≥ 2 * (MIN_EDGE_LEN + WORK_W/2 + TX_W/2)
//          = 2 * (200 + 110 + 100) = 820. Use 900 for headroom.
export const MIN_EDGE_LEN = 200;
export const MIN_REGION_W = 900;
export const PAD_X = 260;
export const WORK_GAP = 80;
export const PORT_OFFSET = 220;

// y inside a region (region origin = top-left of the parent group)
export const Y_HEADER_TOP = REGION_PAD_TOP;
export const Y_HEADER_BOTTOM = Y_HEADER_TOP + HEADER_H;
export const Y_INPUTS_TOP = Y_HEADER_BOTTOM + 12;
export const Y_INPUTS_BOTTOM = Y_INPUTS_TOP + INPUTS_BAND_H;
export const Y_OUTPUTS_BOTTOM = REGION_H - REGION_PAD_BOTTOM;
export const Y_OUTPUTS_TOP = Y_OUTPUTS_BOTTOM - OUTPUTS_BAND_H;
export const Y_OUTPUTS_DIV = Y_OUTPUTS_TOP - 12;
export const Y_WORK = (Y_INPUTS_BOTTOM + Y_OUTPUTS_DIV) / 2;
// Deep south Y for return-flow edges. Backflow is INTRA-band (loop
// within a single workflow), so it sits in the inner lane — closer to
// the work line than cross-workflow links, which jump to the inter-band
// gutter. Pulled in from the original "2 * WORK_H" spec so backflow
// reads as the tighter, semantically-closer lane.
export const Y_DEEP_RETURN = Math.min(
  Y_WORK + WORK_H + 32,
  Y_OUTPUTS_TOP - 30,
);
export const Y_DETOUR_RETURN = Y_WORK + (Y_OUTPUTS_DIV - Y_WORK) / 2;
export const Y_DETOUR_SIDE = Y_INPUTS_BOTTOM + (Y_WORK - Y_INPUTS_BOTTOM) / 2;

// ── data passed into custom node components ───────────────────────
export interface StatusNodeData extends Record<string, unknown> {
  status: WorkflowStatus;
  index: number;
  blurb: string;
  terminal: boolean;
  width: number;
  height: number;
  inputsTop: number;
  inputsBottom: number;
  outputsTop: number;
  outputsBottom: number;
  outputsDividerY: number;
  workY: number;
  headerH: number;
}

export interface WorkStepNodeData extends Record<string, unknown> {
  workStep: WorkflowWorkStep;
  statusId: string;
}

export interface ChipNodeData extends Record<string, unknown> {
  kind: "skill" | "ref";
  label: string;
  statusId: string;
  // Set when kind === "skill" — the work_step ids in this region that
  // declare this skill. Multiple work_steps loading the same skill produce
  // a single deduped chip; the array carries the set of producers for
  // click-through.
  workStepIds?: string[];
  artifact?: WorkflowArtifactRef;
}

export interface TileNodeData extends Record<string, unknown> {
  kind: "artifact";
  label: string;
  statusId: string;
  artifact: WorkflowArtifactRef;
}

export interface BoundaryNodeData extends Record<string, unknown> {
  route: WorkflowRoute;
  gateCount: number;
}

export interface DetourNodeData extends Record<string, unknown> {
  route: WorkflowRoute;
  gateCount: number;
}

export interface BranchNodeData extends Record<string, unknown> {
  command: string;
  actor: string;
}

export interface JitNodeData extends Record<string, unknown> {
  id: string;
  statusId: string;
}

export interface PortNodeData extends Record<string, unknown> {
  kind: "source" | "sink";
  label: string;
}

// ── helpers ───────────────────────────────────────────────────────
const chipWidth = (label: string, min: number): number =>
  Math.max(min, Math.ceil(label.length * SKILL_CHIP_W_PER_CHAR) + CHIP_PAD_X * 2);

const sumChips = (labels: string[], min: number): number =>
  labels.length === 0
    ? 0
    : labels.reduce((acc, l) => acc + chipWidth(l, min), 0) +
      CHIP_GAP * (labels.length - 1);

const sumTiles = (n: number): number =>
  n === 0 ? 0 : n * TILE_W + CHIP_GAP * (n - 1);

const isTerminal = (s: WorkflowStatus): boolean => s.next?.kind === "terminal";

const statusBlurb = (s: WorkflowStatus): string => {
  const raw = (s.description ?? s.label ?? "").trim();
  // Don't echo the id back as the blurb.
  if (raw === s.id || raw === s.id.replace(/_/g, " ")) return "";
  return raw;
};

// ── builder ───────────────────────────────────────────────────────
export interface FlowGraph {
  nodes: Node[];
  edges: Edge[];
  width: number;
  height: number;
}

export interface BuildOptions {
  gateMode?: "lock" | "diamond";
  branches?: Record<string, BranchOutcome>;
}

export function buildFlow(
  wf: WorkflowDefinition,
  opts: BuildOptions = {},
): FlowGraph {
  const gateMode = opts.gateMode ?? "diamond";
  const branches = opts.branches ?? BRANCHES;

  // Outputs band — flex grid, max 3 cols. ≤3 → single row; 4-6 → 2 rows;
  // 7-9 → 3 rows; etc. Region grows just enough to fit the tallest grid.
  const MAX_OUTPUT_COLS = 3;
  const OUTPUT_COL_GAP = CHIP_GAP;
  const OUTPUT_ROW_GAP = 8;
  const colsFor = (n: number) => Math.min(MAX_OUTPUT_COLS, Math.max(1, n));
  const rowsFor = (n: number) => Math.ceil(n / colsFor(n));
  const maxProduces = wf.statuses.reduce(
    (m, s) => Math.max(m, s.artifacts?.produces?.length ?? 0),
    0,
  );
  const maxRows = rowsFor(maxProduces);
  const OUTPUT_GRID_H =
    maxProduces === 0
      ? OUTPUTS_BAND_H
      : maxRows * TILE_H + (maxRows - 1) * OUTPUT_ROW_GAP;
  const dynOutputsBandH = Math.max(OUTPUTS_BAND_H, OUTPUT_GRID_H + 16);
  const dynRegionH = Math.max(
    REGION_H,
    Y_OUTPUTS_TOP + dynOutputsBandH + REGION_PAD_BOTTOM,
  );
  const dynOutputsBottom = Y_OUTPUTS_TOP + dynOutputsBandH;

  // 1) Per-region content width.
  const regionWidths = wf.statuses.map((s) => {
    const skillLabels = s.work_steps.flatMap((w) => w.skills);
    const refLabels = (s.artifacts?.consumes ?? []).map((a) => a.label);
    const inputsW =
      sumChips(skillLabels, 70) +
      sumChips(refLabels, REF_CHIP_MIN_W) +
      (skillLabels.length > 0 && refLabels.length > 0 ? CHIP_GAP : 0);
    const workW =
      s.work_steps.length > 0
        ? s.work_steps.length * WORK_W + (s.work_steps.length - 1) * WORK_GAP
        : 0;
    const outputW = sumTiles((s.artifacts?.produces ?? []).length);
    const headerW = Math.max(180, s.id.length * 14 + 40);
    const content = Math.max(inputsW, workW, outputW, headerW, 220);
    return Math.max(MIN_REGION_W, content + REGION_PAD_X * 2);
  });

  // 2) Place regions (touching).
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let cursor = PAD_X;
  const regionPos = new Map<string, { x: number; w: number }>();
  wf.statuses.forEach((s, i) => {
    const w = regionWidths[i] ?? MIN_REGION_W;
    const x = cursor;
    nodes.push({
      id: `status:${s.id}`,
      type: "status",
      position: { x, y: 0 },
      draggable: false,
      selectable: true,
      style: { width: w, height: dynRegionH, zIndex: -1 },
      data: {
        status: s,
        index: i,
        blurb: statusBlurb(s),
        terminal: isTerminal(s),
        width: w,
        height: dynRegionH,
        inputsTop: Y_INPUTS_TOP,
        inputsBottom: Y_INPUTS_BOTTOM,
        outputsTop: Y_OUTPUTS_TOP,
        outputsBottom: dynOutputsBottom,
        outputsDividerY: Y_OUTPUTS_DIV,
        workY: Y_WORK,
        headerH: HEADER_H,
      } satisfies StatusNodeData,
    });
    regionPos.set(s.id, { x, w });
    cursor += w;
    // Dotted vertical divider on the seam between this region and the
    // next one (skip after the last status). Z-index sits between region
    // background (zIndex -1) and the gate/boundary nodes that anchor at
    // Y_WORK along the same seam, so the line reads under the gates.
    if (i < wf.statuses.length - 1) {
      nodes.push({
        id: `divider:${s.id}`,
        type: "divider",
        position: { x: cursor - 0.5, y: 0 },
        draggable: false,
        selectable: false,
        focusable: false,
        zIndex: 0,
        data: { height: dynRegionH },
      });
    }
  });
  const totalWidth = cursor + PAD_X;

  // 3) Per-region children (input chips, work_steps, output tiles, JITs).
  wf.statuses.forEach((s) => {
    const reg = regionPos.get(s.id);
    if (!reg) return;

    // Input chips — laid out as a row centred in the inputs band.
    type ChipItem =
      | {
          kind: "skill";
          id: string;
          label: string;
          workStepIds: string[];
          w: number;
        }
      | {
          kind: "ref";
          id: string;
          label: string;
          artifact: WorkflowArtifactRef;
          w: number;
        };
    // Dedupe skills BY NAME within a region. The data model lets each
    // work_step independently declare skills, so when two steps in a status
    // both load `backend-development` we naturally get two raw entries —
    // visually noisy. The truth is "this skill is loaded in this region";
    // the set of work_steps that load it is metadata for click-through.
    const skillToWorkSteps = new Map<string, string[]>();
    s.work_steps.forEach((w) => {
      w.skills.forEach((sk) => {
        const list = skillToWorkSteps.get(sk) ?? [];
        if (!list.includes(w.id)) list.push(w.id);
        skillToWorkSteps.set(sk, list);
      });
    });
    const items: ChipItem[] = [
      ...Array.from(skillToWorkSteps.entries()).map(([sk, workStepIds]) => ({
        kind: "skill" as const,
        id: `chip:${s.id}:skill:${sk}`,
        label: sk,
        workStepIds,
        w: chipWidth(sk, 70),
      })),
      ...(s.artifacts?.consumes ?? []).map((a, k) => ({
        kind: "ref" as const,
        id: `chip:${s.id}:ref:${a.id}:${k}`,
        label: a.label,
        artifact: a,
        w: chipWidth(a.label, REF_CHIP_MIN_W),
      })),
    ];
    if (items.length > 0) {
      const total = items.reduce((a, b) => a + b.w, 0) + CHIP_GAP * (items.length - 1);
      let x = reg.w / 2 - total / 2;
      const y = Y_INPUTS_TOP + (INPUTS_BAND_H - CHIP_H) / 2;
      items.forEach((it) => {
        const data: ChipNodeData = {
          kind: it.kind,
          label: it.label,
          statusId: s.id,
        };
        if (it.kind === "skill") data.workStepIds = it.workStepIds;
        if (it.kind === "ref") data.artifact = it.artifact;
        nodes.push({
          id: it.id,
          type: "chip",
          parentId: `status:${s.id}`,
          extent: "parent",
          position: { x, y },
          draggable: false,
          selectable: false,
          style: { width: it.w, height: CHIP_H, zIndex: 5 },
          data: data as Record<string, unknown>,
        });
        x += it.w + CHIP_GAP;
      });
    }

    // Work_steps — centred on the work-Y line.
    if (s.work_steps.length > 0) {
      const total =
        s.work_steps.length * WORK_W + (s.work_steps.length - 1) * WORK_GAP;
      let x = reg.w / 2 - total / 2;
      s.work_steps.forEach((w) => {
        nodes.push({
          id: `work:${s.id}:${w.id}`,
          type: "workStep",
          parentId: `status:${s.id}`,
          extent: "parent",
          position: { x, y: Y_WORK - WORK_H / 2 },
          draggable: false,
          selectable: true,
          style: { width: WORK_W, height: WORK_H, zIndex: 6 },
          data: {
            workStep: w,
            statusId: s.id,
          } satisfies WorkStepNodeData,
        });
        x += WORK_W + WORK_GAP;
      });
    }

    // JIT prompts as small flares above the first work_step (or region centre).
    if (s.jit_prompts.length > 0) {
      const ws = s.work_steps[0];
      const anchorX = ws ? reg.w / 2 : reg.w / 2;
      const anchorY = ws
        ? Y_WORK - WORK_H / 2 - JIT_W - 8
        : Y_WORK - WORK_H - JIT_W;
      const total = s.jit_prompts.length * JIT_W + (s.jit_prompts.length - 1) * JIT_GAP;
      let x = anchorX - total / 2;
      s.jit_prompts.forEach((id) => {
        nodes.push({
          id: `jit:${s.id}:${id}`,
          type: "jit",
          parentId: `status:${s.id}`,
          extent: "parent",
          position: { x, y: anchorY },
          draggable: false,
          selectable: true,
          style: { width: JIT_W, height: JIT_W, zIndex: 7 },
          data: {
            id,
            statusId: s.id,
          } satisfies JitNodeData,
        });
        x += JIT_W + JIT_GAP;
      });
    }

    // Output tiles — flex grid: cols = min(count, MAX_OUTPUT_COLS), rows wrap.
    const produces = s.artifacts?.produces ?? [];
    if (produces.length > 0) {
      const cols = colsFor(produces.length);
      const rows = rowsFor(produces.length);
      const gridW = cols * TILE_W + (cols - 1) * OUTPUT_COL_GAP;
      const gridH = rows * TILE_H + (rows - 1) * OUTPUT_ROW_GAP;
      const startX = reg.w / 2 - gridW / 2;
      const startY = Y_OUTPUTS_TOP + (dynOutputsBandH - gridH) / 2;
      produces.forEach((a, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        // Centre the last (possibly-short) row.
        const itemsInRow =
          row === rows - 1 && produces.length % cols !== 0
            ? produces.length % cols
            : cols;
        const rowW = itemsInRow * TILE_W + (itemsInRow - 1) * OUTPUT_COL_GAP;
        const rowStartX = reg.w / 2 - rowW / 2;
        const x =
          itemsInRow === cols
            ? startX + col * (TILE_W + OUTPUT_COL_GAP)
            : rowStartX + col * (TILE_W + OUTPUT_COL_GAP);
        const y = startY + row * (TILE_H + OUTPUT_ROW_GAP);
        nodes.push({
          id: `tile:${s.id}:${a.id}`,
          type: "tile",
          parentId: `status:${s.id}`,
          extent: "parent",
          position: { x, y },
          draggable: false,
          selectable: true,
          style: { width: TILE_W, height: TILE_H, zIndex: 5 },
          data: {
            kind: "artifact",
            label: a.label,
            statusId: s.id,
            artifact: a,
          } satisfies TileNodeData,
        });
      });
    }
  });

  // 4) Branched outcomes — group by command.
  const branchGroups = new Map<string, Array<{ route: WorkflowRoute; outcome: string }>>();
  wf.routes.forEach((r) => {
    const b = branches[r.id];
    if (!b) return;
    const list = branchGroups.get(b.branchOf) ?? [];
    list.push({ route: r, outcome: b.outcome });
    branchGroups.set(b.branchOf, list);
  });
  const diamondCx = new Map<string, number>();
  if (gateMode === "diamond") {
    branchGroups.forEach((outcomes, command) => {
      const first = outcomes[0];
      if (!first) return;
      const reg = regionPos.get(first.route.from);
      if (!reg) return;
      const cx = reg.x + reg.w; // wall east of source region
      nodes.push({
        id: `branch:${command}`,
        type: "branch",
        position: { x: cx - 60, y: Y_WORK - 32 },
        draggable: false,
        selectable: true,
        style: { width: 120, height: 64, zIndex: 8 },
        data: {
          command,
          actor: first.route.actor,
        } satisfies BranchNodeData,
      });
      diamondCx.set(command, cx);
    });
  }

  // 5) Transitions (boundary / detour) and their edges.
  // Build per-region traffic maps for explicit-edge wiring (step 6).
  // Both maps use Sets so multiple branch outcomes from the same source don't
  // produce duplicate edges (same diamond node id from many outcomes).
  const incomingByRegion = new Map<string, Set<string>>();
  const outgoingByRegion = new Map<string, Set<string>>();
  const noteIn = (statusId: string, sourceNodeId: string) => {
    const set = incomingByRegion.get(statusId) ?? new Set<string>();
    set.add(sourceNodeId);
    incomingByRegion.set(statusId, set);
  };
  const noteOut = (statusId: string, targetNodeId: string) => {
    const set = outgoingByRegion.get(statusId) ?? new Set<string>();
    set.add(targetNodeId);
    outgoingByRegion.set(statusId, set);
  };

  wf.routes.forEach((r) => {
    const branchInfo = branches[r.id];
    const isBranchOutcome = gateMode === "diamond" && Boolean(branchInfo);
    const sourceFrom = r.from.startsWith("source:");
    const sinkTo = r.to.startsWith("sink:");
    const isForwardLike = r.kind === "forward" || r.kind === "terminal";
    const fromReg = regionPos.get(r.from);
    const toReg = regionPos.get(r.to);

    if (isBranchOutcome && branchInfo) {
      // The branch outcome edge itself is emitted in step 7 (via the
      // through-region wiring) so it isn't duplicated. Just note traffic.
      if (fromReg) noteOut(r.from, `branch:${branchInfo.branchOf}`);
      if (toReg && !sinkTo) noteIn(r.to, `branch:${branchInfo.branchOf}`);
      // For sink-bound outcomes (rare) keep an explicit edge.
      if (sinkTo) {
        edges.push({
          id: `e:${r.id}`,
          source: `branch:${branchInfo.branchOf}`,
          target: `port:${r.to}`,
          sourceHandle: "right",
          targetHandle: "left",
          type: "actor",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: actorStrokeColor(r.actor),
            width: 16,
            height: 16,
          },
          data: { actor: r.actor, kind: r.kind, label: branchInfo.outcome },
        });
      }
      return;
    }

    if (isForwardLike) {
      let cx: number;
      if (sourceFrom && toReg) {
        // Source-from: place the tx INSIDE the first region's west edge
        // (no real wall to the west).
        cx = toReg.x + TX_W / 2 + 32;
      } else if (sinkTo && fromReg) {
        // Sink-to: place the tx INSIDE the last region's east edge.
        cx = fromReg.x + fromReg.w - TX_W / 2 - 32;
      } else if (fromReg && toReg) {
        cx = fromReg.x + fromReg.w; // wall between fromReg and toReg
      } else {
        cx = totalWidth / 2;
      }
      nodes.push({
        id: `tx:${r.id}`,
        type: "boundary",
        position: { x: cx - TX_W / 2, y: Y_WORK - TX_H / 2 },
        draggable: false,
        selectable: true,
        style: { width: TX_W, height: TX_H, zIndex: 10 },
        data: {
          route: r,
          gateCount:
            (r.controls?.validators?.length ?? 0) +
            (r.controls?.prompt_checks?.length ?? 0),
        } satisfies BoundaryNodeData,
      });
      // Mark the tx as outgoing from `from` (or port) and incoming to `to` (or port).
      if (fromReg) noteOut(r.from, `tx:${r.id}`);
      if (toReg) noteIn(r.to, `tx:${r.id}`);
      return;
    }

    // Detour route — return / side / loop. Position in the appropriate detour lane,
    // midway between the two regions.
    const fromX = fromReg ? fromReg.x + fromReg.w / 2 : 0;
    const toX = toReg ? toReg.x + toReg.w / 2 : totalWidth;
    const cx = (fromX + toX) / 2;
    const cy = r.kind === "return" ? Y_DETOUR_RETURN : Y_DETOUR_SIDE;
    nodes.push({
      id: `tx:${r.id}`,
      type: "detour",
      position: { x: cx - TX_W / 2, y: cy - TX_H / 2 },
      draggable: false,
      selectable: true,
      style: { width: TX_W, height: TX_H, zIndex: 10 },
      data: {
        route: r,
        gateCount:
          (r.controls?.validators?.length ?? 0) +
          (r.controls?.prompt_checks?.length ?? 0),
      } satisfies DetourNodeData,
    });
    if (fromReg) noteOut(r.from, `tx:${r.id}`);
    if (toReg) noteIn(r.to, `tx:${r.id}`);
  });

  // 6) Source/sink ports.
  const seen = new Set<string>();
  wf.routes.forEach((r) => {
    if (r.from.startsWith("source:") && !seen.has(r.from)) {
      // Port lives in the west margin, well clear of the first region's
      // source-from boundary transition (which sits inside the region's
      // west edge). Targets MIN_EDGE_LEN of clear edge between port and tx.
      nodes.push({
        id: `port:${r.from}`,
        type: "port",
        position: { x: PAD_X - PORT_OFFSET, y: Y_WORK - 18 },
        draggable: false,
        selectable: true,
        style: { width: 36, height: 36, zIndex: 9 },
        data: {
          kind: "source",
          label: r.from.replace("source:", ""),
        } satisfies PortNodeData,
      });
      seen.add(r.from);
    }
    if (r.to.startsWith("sink:") && !seen.has(r.to)) {
      nodes.push({
        id: `port:${r.to}`,
        type: "port",
        position: { x: totalWidth - PAD_X + PORT_OFFSET - 36, y: Y_WORK - 18 },
        draggable: false,
        selectable: true,
        style: { width: 36, height: 36, zIndex: 9 },
        data: {
          kind: "sink",
          label: r.to.replace("sink:", ""),
        } satisfies PortNodeData,
      });
      seen.add(r.to);
    }
  });

  // 7) Explicit flow edges:
  //   port:source → tx (forward routes from a source)
  //   tx          → port:sink (forward routes to a sink)
  //   tx_in       → work_step (or region anchor) → tx_out (chain through the region)
  //   work_step   → branch:command (when the source region is a branch source)
  // Every edge is an `actor` edge with a coloured arrow head.
  wf.routes.forEach((r) => {
    const sourceFrom = r.from.startsWith("source:");
    const sinkTo = r.to.startsWith("sink:");
    const isForwardLike = r.kind === "forward" || r.kind === "terminal";
    if (!isForwardLike) return;
    if (sourceFrom) {
      edges.push(
        flowEdge(`e:port-in:${r.id}`, `port:${r.from}`, `tx:${r.id}`, r),
      );
    }
    if (sinkTo) {
      edges.push(
        flowEdge(`e:port-out:${r.id}`, `tx:${r.id}`, `port:${r.to}`, r),
      );
    }
  });

  // For each region: chain incoming → work_step (or anchor) → outgoing.
  wf.statuses.forEach((s) => {
    const incoming = Array.from(incomingByRegion.get(s.id) ?? []);
    const outgoing = Array.from(outgoingByRegion.get(s.id) ?? []);
    if (incoming.length === 0 && outgoing.length === 0) return;

    // Pick a single "midpoint" through which all incoming/outgoing edges pass:
    // first work_step if any, otherwise an invisible region anchor.
    const ws = s.work_steps[0];
    let midpointId: string;
    if (ws) {
      midpointId = `work:${s.id}:${ws.id}`;
    } else {
      midpointId = `region-anchor:${s.id}`;
      if (!nodes.find((n) => n.id === midpointId)) {
        const reg = regionPos.get(s.id);
        nodes.push({
          id: midpointId,
          type: "anchor",
          parentId: `status:${s.id}`,
          extent: "parent",
          position: { x: (reg?.w ?? 0) / 2 - 1, y: Y_WORK - 1 },
          draggable: false,
          selectable: false,
          data: {},
          style: { width: 2, height: 2, opacity: 0 },
        });
      }
    }

    incoming.forEach((src) => {
      let route = findRouteForNode(wf, src);
      // If the source is a branch diamond and we're landing in this region,
      // surface the matching outcome as the edge's label and use the route's
      // own actor/kind so dashed return styling kicks in.
      let label: string | undefined;
      let isReturnFromBranch = false;
      if (src.startsWith("branch:")) {
        const command = src.replace("branch:", "");
        const outcome = branchGroups
          .get(command)
          ?.find((o) => o.route.to === s.id);
        label = outcome?.outcome;
        if (outcome) {
          route = outcome.route;
          isReturnFromBranch = outcome.route.kind === "return";
        }
      }
      // For return-kind outcomes, route the edge via the deep south
      // detour using a custom 'return' edge — explicit step path through
      // Y_DEEP_RETURN with the label well below the work line.
      if (isReturnFromBranch) {
        edges.push(
          flowEdge(
            `e:in:${s.id}:${src}`,
            src,
            midpointId,
            route ?? defaultRoute(wf.actor),
            label,
            { sourceHandle: "bottom", targetHandle: "bottom", type: "return" },
          ),
        );
      } else {
        edges.push(
          flowEdge(
            `e:in:${s.id}:${src}`,
            src,
            midpointId,
            route ?? defaultRoute(wf.actor),
            label,
          ),
        );
      }
    });
    outgoing.forEach((dst) => {
      const route = findRouteForNode(wf, dst);
      edges.push(
        flowEdge(
          `e:out:${s.id}:${dst}`,
          midpointId,
          dst,
          route ?? defaultRoute(wf.actor),
        ),
      );
    });
  });

  return { nodes, edges, width: totalWidth, height: dynRegionH };
}

// ── unified flow: stack all workflows vertically into one canvas ─────

/** Vertical gap between adjacent bands. Cross-workflow edges route in
 *  this gutter (and in the cross-link lane just above each band). */
export const BAND_GUTTER = 140;

/** Cross-link lane sits this far above each band's top, so cross-edges
 *  dock at the band's north *outside* the inputs band (which lives
 *  below the region's top stripe). */
export const CROSSLINK_LANE_OFFSET = 36;

/** Distance from the canvas's left edge to the cross-link "bus" — a
 *  vertical lane shared by every cross-workflow link. Routing every
 *  cross-link through this single lane keeps them out of the bands they
 *  don't terminate at. The lane sits in the negative-x margin so it
 *  doesn't push the bands themselves rightwards. */
export const CROSSLINK_BUS_X = -120;

/** Pixel size of the small endpoint circle rendered on a status's
 *  south/north edge where a cross-link starts/ends. */
export const CROSSLINK_DOT_SIZE = 14;

export interface BandInfo {
  workflowId: string;
  bandTop: number;
  width: number;
  height: number;
  parentNodeId: string;
  briefDescription: string;
}

export interface UnifiedFlowGraph {
  nodes: Node[];
  edges: Edge[];
  width: number;
  height: number;
  bands: BandInfo[];
}

export interface BandNodeData extends Record<string, unknown> {
  workflowId: string;
  brief: string;
  width: number;
  height: number;
}

/** Build a unified ReactFlow graph stacking every workflow in `graph`
 *  as a horizontal band. Each band reuses `buildFlow()` for its own
 *  layout; this function namespaces ids and wraps each band in a
 *  parent group so the navigator can `fitView({ nodes: [{ id: 'band:<wf>' }] })`.
 *
 *  Cross-workflow edges declared via `status.cross_links` are emitted
 *  here (one edge per link) — they require knowledge of multiple bands
 *  so they can't be produced inside a per-band buildFlow.
 */
export function buildUnifiedFlow(
  graph: WorkflowGraph,
  opts: BuildOptions = {},
): UnifiedFlowGraph {
  const allNodes: Node[] = [];
  const allEdges: Edge[] = [];
  const bands: BandInfo[] = [];
  let cursorY = 0;
  let maxWidth = 0;

  // Map (workflowId, statusId) → namespaced status node id, so cross-link
  // edges can find the correct target across bands.
  const statusNodeIdByLink = new Map<string, string>();
  // Map (workflowId, statusId) → ordered list of namespaced work_step
  // ids (in declared order). Used to anchor cross-link dots to the
  // *specific* work_step that triggers / receives the handoff (default:
  // last work_step on source side, first on target side).
  const workStepIdsByStatus = new Map<string, string[]>();

  for (const wf of graph.workflows) {
    const sub = buildFlow(wf, opts);
    const ns = `band:${wf.id}:`;
    const bandParentId = `band:${wf.id}`;

    // Band parent group — invisible holder used for navigator fitView
    // and for the band header ribbon. Children inherit position.
    allNodes.push({
      id: bandParentId,
      type: "band",
      position: { x: 0, y: cursorY },
      draggable: false,
      selectable: false,
      focusable: false,
      style: { width: sub.width, height: sub.height, pointerEvents: "none" },
      data: {
        workflowId: wf.id,
        brief: wf.brief_description ?? "",
        width: sub.width,
        height: sub.height,
      } satisfies BandNodeData,
      zIndex: -100,
    });

    for (const n of sub.nodes) {
      const newId = `${ns}${n.id}`;
      const isTopLevel = !n.parentId;
      const newParentId = n.parentId ? `${ns}${n.parentId}` : bandParentId;
      allNodes.push({
        ...n,
        id: newId,
        parentId: newParentId,
        extent: isTopLevel ? "parent" : n.extent,
      });
      if (n.id.startsWith("status:")) {
        const statusId = n.id.slice("status:".length);
        statusNodeIdByLink.set(`${wf.id}|${statusId}`, newId);
      } else if (n.id.startsWith("work:")) {
        // n.id format: `work:<statusId>:<workStepId>`
        const rest = n.id.slice("work:".length);
        const colon = rest.indexOf(":");
        if (colon !== -1) {
          const statusId = rest.slice(0, colon);
          const key = `${wf.id}|${statusId}`;
          const list = workStepIdsByStatus.get(key) ?? [];
          list.push(newId);
          workStepIdsByStatus.set(key, list);
        }
      }
    }
    for (const e of sub.edges) {
      allEdges.push({
        ...e,
        id: `${ns}${e.id}`,
        source: `${ns}${e.source}`,
        target: `${ns}${e.target}`,
      });
    }

    bands.push({
      workflowId: wf.id,
      bandTop: cursorY,
      width: sub.width,
      height: sub.height,
      parentNodeId: bandParentId,
      briefDescription: wf.brief_description ?? "",
    });
    maxWidth = Math.max(maxWidth, sub.width);
    cursorY += sub.height + BAND_GUTTER;
  }

  // Cross-workflow edges + clickable endpoint dots. Read from each
  // status's `cross_links` (always canonical on the source side per the
  // schema convention).
  for (const wf of graph.workflows) {
    for (const status of wf.statuses) {
      const links = status.cross_links ?? [];
      for (let i = 0; i < links.length; i += 1) {
        const link = links[i];
        if (!link || link.kind === "triggered_by") continue;
        // Anchor parents: prefer the SPECIFIC work_step that triggers /
        // receives the handoff. Default — source side: the LAST work_step
        // of the source status (the work the actor finishes before
        // triggering); target side: the FIRST work_step of the target
        // status (the entry-point work for the incoming handoff). Fall
        // back to the status region if a side has no work_steps.
        const srcWorkSteps = workStepIdsByStatus.get(`${wf.id}|${status.id}`) ?? [];
        const tgtWorkSteps =
          workStepIdsByStatus.get(`${link.workflow}|${link.status}`) ?? [];
        const sourceParentId =
          srcWorkSteps[srcWorkSteps.length - 1] ??
          statusNodeIdByLink.get(`${wf.id}|${status.id}`);
        const targetParentId =
          tgtWorkSteps[0] ??
          statusNodeIdByLink.get(`${link.workflow}|${link.status}`);
        if (!sourceParentId || !targetParentId) continue;

        // Emit source + target endpoint dots, parented to the specific
        // work_step (or fallback region) on each side. Click handler on
        // each dot jumps to the OTHER endpoint's band (wired in
        // WorkflowFlowchart).
        const srcDotId = `xdot:src:${wf.id}:${status.id}:${i}`;
        const tgtDotId = `xdot:tgt:${wf.id}:${status.id}:${i}`;
        const srcParent = allNodes.find((n) => n.id === sourceParentId);
        const tgtParent = allNodes.find((n) => n.id === targetParentId);
        const srcW = (srcParent?.style as { width?: number } | undefined)
          ?.width ?? WORK_W;
        const srcH = (srcParent?.style as { height?: number } | undefined)
          ?.height ?? WORK_H;
        const tgtW = (tgtParent?.style as { width?: number } | undefined)
          ?.width ?? WORK_W;
        // South dot at the bottom-centre of the source work_step (or
        // region fallback). Explicit width/height so ReactFlow can
        // measure; pointerEvents:auto overrides the band's "none".
        allNodes.push({
          id: srcDotId,
          type: "crosslinkEndpoint",
          parentId: sourceParentId,
          position: {
            x: srcW / 2 - CROSSLINK_DOT_SIZE / 2,
            y: srcH - CROSSLINK_DOT_SIZE / 2,
          },
          draggable: false,
          selectable: false,
          focusable: false,
          zIndex: 100,
          style: {
            width: CROSSLINK_DOT_SIZE,
            height: CROSSLINK_DOT_SIZE,
            pointerEvents: "auto",
          },
          data: {
            role: "source",
            otherWorkflowId: link.workflow,
            otherStatusId: link.status,
            label: link.label ?? null,
          },
        });
        // North dot at the top-centre of the target work_step (or
        // region fallback).
        allNodes.push({
          id: tgtDotId,
          type: "crosslinkEndpoint",
          parentId: targetParentId,
          position: {
            x: tgtW / 2 - CROSSLINK_DOT_SIZE / 2,
            y: -CROSSLINK_DOT_SIZE / 2,
          },
          draggable: false,
          selectable: false,
          focusable: false,
          zIndex: 100,
          style: {
            width: CROSSLINK_DOT_SIZE,
            height: CROSSLINK_DOT_SIZE,
            pointerEvents: "auto",
          },
          data: {
            role: "target",
            otherWorkflowId: wf.id,
            otherStatusId: status.id,
            label: link.label ?? null,
          },
        });

        // Edge connects the dots. Path is drawn by CrossLinkEdge, which
        // routes through the left bus (CROSSLINK_BUS_X) so the line
        // never crosses a status region it doesn't terminate at. We
        // pass the source band's south Y and target band's north Y in
        // the edge's data so the edge can route its horizontal segments
        // through the BAND_GUTTER (between bands) instead of within
        // the band itself — which puts it OUTSIDE the band's outputs
        // grid and clearly past the inner backflow lane.
        const srcBand = bands.find((b) => b.workflowId === wf.id);
        const tgtBand = bands.find((b) => b.workflowId === link.workflow);
        allEdges.push({
          id: `xlink:${wf.id}:${status.id}:${i}`,
          type: "crosslink",
          source: srcDotId,
          target: tgtDotId,
          sourceHandle: "south",
          targetHandle: "north",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: "#0e7c8a",
            width: 14,
            height: 14,
          },
          data: {
            sourceWorkflow: wf.id,
            label: link.label ?? null,
            sourceBandSouthY: srcBand
              ? srcBand.bandTop + srcBand.height
              : null,
            targetBandNorthY: tgtBand ? tgtBand.bandTop : null,
          },
          zIndex: 1,
        });
      }
    }
  }

  return {
    nodes: allNodes,
    edges: allEdges,
    width: maxWidth,
    height: cursorY > 0 ? cursorY - BAND_GUTTER : 0,
    bands,
  };
}

function flowEdge(
  id: string,
  source: string,
  target: string,
  r: WorkflowRoute,
  label?: string,
  handles:
    | { sourceHandle?: string; targetHandle?: string; type?: string }
    | undefined = undefined,
): Edge {
  return {
    id,
    source,
    target,
    sourceHandle: handles?.sourceHandle ?? "right",
    targetHandle: handles?.targetHandle ?? "left",
    type: handles?.type ?? "actor",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: actorStrokeColor(r.actor),
      width: 14,
      height: 14,
    },
    data: { actor: r.actor, kind: r.kind, label },
  };
}

function findRouteForNode(
  wf: WorkflowDefinition,
  nodeId: string,
): WorkflowRoute | undefined {
  if (nodeId.startsWith("tx:")) {
    const rid = nodeId.replace("tx:", "");
    return wf.routes.find((r) => r.id === rid);
  }
  if (nodeId.startsWith("branch:")) {
    const command = nodeId.replace("branch:", "");
    return wf.routes.find((r) => r.command === command);
  }
  return undefined;
}

function defaultRoute(actor: string): WorkflowRoute {
  return {
    id: "default",
    workflow_id: "default",
    actor,
    from: "default",
    to: "default",
    kind: "forward",
    label: "",
    controls: { validators: [], jit_prompts: [], prompt_checks: [] },
    skills: [],
    emits: { artifacts: [], events: [], comments: [], status_changes: [] },
  };
}
