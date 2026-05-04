// Alternate layout: lay the workflow out with dagre (LR direction) instead
// of the hand-rolled swim-lane positioning in flowGraph.ts. Opt-in via
// ?layout=dagre on the workflow page. Useful as a sanity-check view and
// for workflows whose content variance breaks the swim-lane assumptions.

import { graphlib, layout as dagreLayout } from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type {
  WorkflowDefinition,
  WorkflowRoute,
} from "@/lib/api/endpoints/workflow";
import { BRANCHES } from "./decorations";
import {
  TX_H,
  TX_W,
  WORK_H,
  WORK_W,
  type BoundaryNodeData,
  type BranchNodeData,
  type DetourNodeData,
  type StatusNodeData,
  type WorkStepNodeData,
} from "./flowGraph";
import { ACTOR_COLOR, isKnownActor } from "./tokens";

const STATUS_NODE_W = 220;
const STATUS_NODE_H = 80;

const actorStroke = (actor: string): string =>
  isKnownActor(actor) ? ACTOR_COLOR[actor] : "var(--color-ink)";

export interface FlowGraph {
  nodes: Node[];
  edges: Edge[];
  width: number;
  height: number;
}

export function buildFlowDagre(wf: WorkflowDefinition): FlowGraph {
  // Build a graphlib instance with one node per status, work_step, boundary,
  // branch diamond. Edges = forward routes + branch outcome edges + detour
  // routes. Then dagre lays it out left-to-right.
  const g = new graphlib.Graph();
  g.setGraph({
    rankdir: "LR",
    nodesep: 120,
    ranksep: 240,
    edgesep: 40,
    marginx: 80,
    marginy: 80,
  });
  g.setDefaultEdgeLabel(() => ({}));

  // status placeholders — these become slim header tiles in dagre's coords
  wf.statuses.forEach((s) => {
    g.setNode(`status:${s.id}`, { width: STATUS_NODE_W, height: STATUS_NODE_H });
    s.work_steps.forEach((ws) => {
      g.setNode(`work:${s.id}:${ws.id}`, { width: WORK_W, height: WORK_H });
      // wire the work_step into the status's rank
      g.setEdge(`status:${s.id}`, `work:${s.id}:${ws.id}`);
    });
  });

  // branch diamonds
  const branchGroups = new Map<string, WorkflowRoute[]>();
  wf.routes.forEach((r) => {
    const b = BRANCHES[r.id];
    if (!b) return;
    const list = branchGroups.get(b.branchOf) ?? [];
    list.push(r);
    branchGroups.set(b.branchOf, list);
  });
  branchGroups.forEach((_outcomes, command) => {
    g.setNode(`branch:${command}`, { width: 120, height: 64 });
  });

  // boundary + detour transitions and edges
  wf.routes.forEach((r) => {
    const branchInfo = BRANCHES[r.id];
    const isBranchOutcome = Boolean(branchInfo);
    const sourceFrom = r.from.startsWith("source:");
    const sinkTo = r.to.startsWith("sink:");
    const isForwardLike = r.kind === "forward" || r.kind === "terminal";

    if (isBranchOutcome && branchInfo) {
      const fromBranch = `branch:${branchInfo.branchOf}`;
      const toNode = sinkTo
        ? `port:${r.to}`
        : `status:${r.to}`;
      if (sinkTo) g.setNode(toNode, { width: 40, height: 40 });
      g.setEdge(fromBranch, toNode);
      // wire branch into source region rank
      g.setEdge(`status:${r.from}`, fromBranch);
      return;
    }

    if (isForwardLike) {
      g.setNode(`tx:${r.id}`, { width: TX_W, height: TX_H });
      const from = sourceFrom
        ? (() => {
            g.setNode(`port:${r.from}`, { width: 40, height: 40 });
            return `port:${r.from}`;
          })()
        : `status:${r.from}`;
      const to = sinkTo
        ? (() => {
            g.setNode(`port:${r.to}`, { width: 40, height: 40 });
            return `port:${r.to}`;
          })()
        : `status:${r.to}`;
      g.setEdge(from, `tx:${r.id}`);
      g.setEdge(`tx:${r.id}`, to);
      return;
    }

    // detour
    g.setNode(`tx:${r.id}`, { width: TX_W, height: TX_H });
    const from = `status:${r.from}`;
    const to = `status:${r.to}`;
    g.setEdge(from, `tx:${r.id}`);
    g.setEdge(`tx:${r.id}`, to);
  });

  dagreLayout(g);

  // Convert dagre output into ReactFlow nodes (top-left positioning).
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const statusById = new Map(wf.statuses.map((s) => [s.id, s]));

  g.nodes().forEach((id) => {
    const meta = g.node(id);
    if (!meta) return;
    const x = Math.round(meta.x - meta.width / 2);
    const y = Math.round(meta.y - meta.height / 2);

    if (id.startsWith("status:")) {
      const sid = id.replace("status:", "");
      const s = statusById.get(sid);
      if (!s) return;
      nodes.push({
        id,
        type: "status",
        position: { x, y },
        draggable: false,
        selectable: true,
        style: { width: meta.width, height: meta.height, zIndex: -1 },
        data: {
          status: s,
          index: wf.statuses.findIndex((ss) => ss.id === sid),
          blurb: s.description ?? "",
          terminal: s.next?.kind === "terminal",
          width: meta.width,
          height: meta.height,
          inputsTop: 0,
          inputsBottom: 0,
          outputsTop: 0,
          outputsBottom: 0,
          outputsDividerY: 0,
          workY: 0,
          headerH: meta.height,
        } satisfies StatusNodeData,
      });
      return;
    }

    if (id.startsWith("work:")) {
      const [, statusId, wsId] = id.split(":");
      const s = statusById.get(statusId!);
      const ws = s?.work_steps.find((w) => w.id === wsId);
      if (!s || !ws) return;
      nodes.push({
        id,
        type: "workStep",
        position: { x, y },
        draggable: false,
        selectable: true,
        style: { width: meta.width, height: meta.height, zIndex: 6 },
        data: { workStep: ws, statusId: s.id } satisfies WorkStepNodeData,
      });
      return;
    }

    if (id.startsWith("branch:")) {
      const command = id.replace("branch:", "");
      const outcomes = branchGroups.get(command);
      const actor = outcomes?.[0]?.actor ?? "pm-agent";
      nodes.push({
        id,
        type: "branch",
        position: { x, y },
        draggable: false,
        selectable: true,
        style: { width: meta.width, height: meta.height, zIndex: 8 },
        data: { command, actor } satisfies BranchNodeData,
      });
      return;
    }

    if (id.startsWith("tx:")) {
      const routeId = id.replace("tx:", "");
      const r = wf.routes.find((rr) => rr.id === routeId);
      if (!r) return;
      const isForwardLike = r.kind === "forward" || r.kind === "terminal";
      const gateCount =
        (r.controls?.validators?.length ?? 0) +
        (r.controls?.prompt_checks?.length ?? 0);
      nodes.push({
        id,
        type: isForwardLike ? "boundary" : "detour",
        position: { x, y },
        draggable: false,
        selectable: true,
        style: { width: meta.width, height: meta.height, zIndex: 10 },
        data: { route: r, gateCount } satisfies BoundaryNodeData | DetourNodeData,
      });
      return;
    }

    if (id.startsWith("port:")) {
      const ref = id.replace("port:", "");
      const kind = ref.startsWith("source:") ? "source" : "sink";
      const label = ref.replace(/^source:|^sink:/, "");
      nodes.push({
        id,
        type: "port",
        position: { x, y },
        draggable: false,
        selectable: true,
        style: { width: meta.width, height: meta.height, zIndex: 9 },
        data: { kind, label },
      });
      return;
    }
  });

  // Dagre's internal edges — convert to ReactFlow edges (actor colour from
  // matching route, if any).
  g.edges().forEach((e) => {
    // Try to identify an originating route for actor colouring.
    let actor = "pm-agent";
    let kind = "forward";
    let label: string | undefined;
    let routeId: string | undefined;
    if (e.v.startsWith("branch:") && (e.w.startsWith("status:") || e.w.startsWith("port:"))) {
      const command = e.v.replace("branch:", "");
      const target = e.w.replace(/^status:|^port:/, "");
      const route = wf.routes.find((r) => {
        const b = BRANCHES[r.id];
        return b?.branchOf === command && r.to === target;
      });
      if (route) {
        actor = route.actor;
        kind = route.kind;
        label = BRANCHES[route.id]?.outcome;
        routeId = route.id;
      }
    } else if (e.v.startsWith("tx:")) {
      const r = wf.routes.find((rr) => rr.id === e.v.replace("tx:", ""));
      if (r) {
        actor = r.actor;
        kind = r.kind;
        routeId = r.id;
      }
    } else if (e.w.startsWith("tx:")) {
      const r = wf.routes.find((rr) => rr.id === e.w.replace("tx:", ""));
      if (r) {
        actor = r.actor;
        kind = r.kind;
        routeId = r.id;
      }
    }
    edges.push({
      id: `e:${e.v}->${e.w}${routeId ? `:${routeId}` : ""}`,
      source: e.v,
      target: e.w,
      type: "actor",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: actorStroke(actor),
        width: 16,
        height: 16,
      },
      data: { actor, kind, label },
    });
  });

  // Compute total bounds.
  const graphMeta = g.graph();
  return {
    nodes,
    edges,
    width: graphMeta.width ?? 1200,
    height: graphMeta.height ?? 760,
  };
}
