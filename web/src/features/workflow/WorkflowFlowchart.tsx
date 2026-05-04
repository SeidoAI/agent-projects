import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useOnViewportChange,
  useReactFlow,
  type Node,
  type NodeMouseHandler,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  WorkflowArtifactRef,
  WorkflowDefinition,
  WorkflowRegistry,
  WorkflowRoute,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";
import { ActorEdge, ReturnEdge } from "./flowEdges";
import {
  buildFlow,
  type BoundaryNodeData,
  type ChipNodeData,
  type DetourNodeData,
  type JitNodeData,
  type StatusNodeData,
  type TileNodeData,
  type WorkStepNodeData,
} from "./flowGraph";
import { buildFlowDagre } from "./flowGraphDagre";

export type LayoutMode = "territory" | "dagre";
import {
  AnchorNode,
  BoundaryTransitionNode,
  BranchDiamondNode,
  ChipNode,
  DetourTransitionNode,
  JitPromptNode,
  PortNode,
  StatusDividerNode,
  StatusRegionNode,
  TileNode,
  WorkStepNode,
} from "./flowNodes";
import { GatePanel } from "./GatePanel";
import { statusHex, statusTint } from "./tokens";

const NODE_TYPES = {
  status: StatusRegionNode,
  workStep: WorkStepNode,
  chip: ChipNode,
  tile: TileNode,
  boundary: BoundaryTransitionNode,
  detour: DetourTransitionNode,
  branch: BranchDiamondNode,
  jit: JitPromptNode,
  port: PortNode,
  anchor: AnchorNode,
  divider: StatusDividerNode,
};

const EDGE_TYPES = {
  actor: ActorEdge,
  return: ReturnEdge,
};

const DEFAULT_EDGE_OPTIONS = {
  type: "actor",
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
} as const;

const VIEWPORT_STORAGE_PREFIX = "tripwire:workflow-viewport:";

export type FlowSelection =
  | { kind: "status"; status: WorkflowStatus }
  | { kind: "route"; route: WorkflowRoute }
  | { kind: "work_step"; statusId: string; workStepId: string }
  | { kind: "jit_prompt"; id: string; statusId: string }
  | {
      kind: "artifact";
      artifact: WorkflowArtifactRef;
      statusId: string;
      direction: "produces" | "consumes";
    };

export interface WorkflowFlowchartProps {
  workflow: WorkflowDefinition;
  registry?: WorkflowRegistry;
  gateMode?: "lock" | "diamond";
  layout?: LayoutMode;
  onSelect?: (selection: FlowSelection) => void;
}

export function WorkflowFlowchart(props: WorkflowFlowchartProps) {
  return (
    <ReactFlowProvider>
      <FlowInner {...props} />
    </ReactFlowProvider>
  );
}

function FlowInner({
  workflow,
  registry,
  gateMode = "diamond",
  layout = "territory",
  onSelect,
}: WorkflowFlowchartProps) {
  const flow = useMemo(
    () =>
      layout === "dagre"
        ? buildFlowDagre(workflow)
        : buildFlow(workflow, { gateMode }),
    [workflow, gateMode, layout],
  );
  const [openedGateRouteId, setOpenedGateRouteId] = useState<string | null>(null);
  const rf = useReactFlow();
  const nodesInitialized = useNodesInitialized();
  const lastInitFor = useRef<string | null>(null);

  // Restore viewport from sessionStorage on first mount per workflow.
  const storageKey = `${VIEWPORT_STORAGE_PREFIX}${workflow.id}`;
  useEffect(() => {
    if (!nodesInitialized || lastInitFor.current === workflow.id) return;
    lastInitFor.current = workflow.id;
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(storageKey) : null;
    if (raw) {
      try {
        const v = JSON.parse(raw) as Viewport;
        rf.setViewport(v, { duration: 0 });
        return;
      } catch {
        /* fall through to fitView */
      }
    }
    rf.fitView({ padding: 0.08, duration: 200 });
  }, [nodesInitialized, workflow.id, storageKey, rf]);

  // Persist viewport on every settle.
  useOnViewportChange({
    onEnd: (v) => {
      if (typeof window !== "undefined") {
        sessionStorage.setItem(storageKey, JSON.stringify(v));
      }
    },
  });

  const routeById = useMemo(() => {
    const m = new Map<string, WorkflowRoute>();
    workflow.routes.forEach((r) => m.set(r.id, r));
    return m;
  }, [workflow.routes]);

  // Cap the panning extent to the actual content bounds + a small margin.
  // Without this the user can pan into vast empty space at low zoom and
  // get lost. ReactFlow expects flow-space coords ([[minX,minY],[maxX,maxY]]).
  const translateExtent = useMemo<[[number, number], [number, number]]>(() => {
    if (flow.nodes.length === 0) {
      return [
        [-1000, -1000],
        [1000, 1000],
      ];
    }
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;
    for (const n of flow.nodes) {
      // Skip child nodes (positions are relative to parent); top-level
      // status regions cover the whole chart and are sufficient bounds.
      if (n.parentId) continue;
      const x = n.position.x;
      const y = n.position.y;
      const w = (n.width ?? (n.data as { width?: number })?.width ?? 0) as number;
      const h = (n.height ?? (n.data as { height?: number })?.height ?? 0) as number;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x + w > maxX) maxX = x + w;
      if (y + h > maxY) maxY = y + h;
    }
    const MARGIN = 240;
    return [
      [minX - MARGIN, minY - MARGIN],
      [maxX + MARGIN, maxY + MARGIN],
    ];
  }, [flow.nodes]);

  const handleNodeClick: NodeMouseHandler = (event, node) => {
    const target = event.target as HTMLElement;
    const gateBtn = target.closest('[data-testid^="workflow-gate-badge-"]');
    if (gateBtn) {
      const id = gateBtn.getAttribute("data-testid")!.replace("workflow-gate-badge-", "");
      setOpenedGateRouteId((prev) => (prev === id ? null : id));
      return;
    }
    const toolbarBtn = target.closest("[data-toolbar-action]");
    if (toolbarBtn) {
      const action = toolbarBtn.getAttribute("data-toolbar-action");
      if (action === "zoom-to-status") {
        const sid = (node.data as unknown as StatusNodeData).status?.id;
        if (sid) rf.fitView({ nodes: [{ id: `status:${sid}` }], padding: 0.2, duration: 600 });
        return;
      }
      if (action === "zoom-to-node") {
        rf.fitView({ nodes: [{ id: node.id }], padding: 0.4, duration: 500 });
        return;
      }
    }

    if (!onSelect) return;
    switch (node.type) {
      case "status": {
        const d = node.data as unknown as StatusNodeData;
        // Single click on a region: zoom to it AND notify the page (drawer).
        rf.fitView({ nodes: [{ id: node.id }], padding: 0.15, duration: 500 });
        onSelect({ kind: "status", status: d.status });
        break;
      }
      case "workStep": {
        const d = node.data as unknown as WorkStepNodeData;
        onSelect({
          kind: "work_step",
          statusId: d.statusId,
          workStepId: d.workStep.id,
        });
        break;
      }
      case "boundary":
      case "detour": {
        const d = node.data as unknown as BoundaryNodeData | DetourNodeData;
        onSelect({ kind: "route", route: d.route });
        break;
      }
      case "chip": {
        const d = node.data as unknown as ChipNodeData;
        if (d.kind === "ref" && d.artifact) {
          onSelect({
            kind: "artifact",
            artifact: d.artifact,
            statusId: d.statusId,
            direction: "consumes",
          });
        }
        break;
      }
      case "tile": {
        const d = node.data as unknown as TileNodeData;
        onSelect({
          kind: "artifact",
          artifact: d.artifact,
          statusId: d.statusId,
          direction: "produces",
        });
        break;
      }
      case "jit": {
        const d = node.data as unknown as JitNodeData;
        onSelect({ kind: "jit_prompt", id: d.id, statusId: d.statusId });
        break;
      }
    }
  };

  const openedRoute = openedGateRouteId ? routeById.get(openedGateRouteId) : null;

  return (
    <div
      className="relative w-full"
      style={{ height: 760 }}
      data-testid="workflow-flowchart"
      data-workflow={workflow.id}
    >
      <ReactFlow
        nodes={flow.nodes}
        edges={flow.edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        minZoom={0.3}
        maxZoom={1.6}
        translateExtent={translateExtent}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        zoomOnPinch
        zoomOnScroll
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={handleNodeClick}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(26,24,21,0.06)" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(240,238,233,0.6)"
          nodeColor={(n: Node) => minimapFill(n)}
          nodeStrokeColor={(n: Node) => minimapStroke(n)}
          nodeStrokeWidth={1.5}
          nodeBorderRadius={2}
        />
      </ReactFlow>

      {openedRoute && (
        <GatePanel
          route={openedRoute}
          registry={registry}
          onClose={() => setOpenedGateRouteId(null)}
        />
      )}
    </div>
  );
}

// MiniMap renders nodes via SVG `fill` / `stroke` attributes — and CSS
// custom properties (var(--…)) do not resolve when set as raw SVG
// attribute values, only when applied via CSS rules. So everything below
// is a literal hex (statusHex / statusTint return hex/rgba strings).
const PM_HEX = "#a07a3c";
const CODING_HEX = "#3d6b46";
const CODE_HEX = "#3a4a85";
const INK_3 = "#7a7368";

function minimapFill(node: Node): string {
  switch (node.type) {
    case "status": {
      const id = (node.data as { status?: { id?: string } })?.status?.id ?? "";
      return statusTint(id, 0.22);
    }
    case "workStep":
      return CODING_HEX;
    case "boundary":
      return PM_HEX;
    case "detour":
      return CODE_HEX;
    case "branch":
      return PM_HEX;
    case "jit":
      return PM_HEX;
    case "tile":
      return "#e8e3d8";
    case "chip":
      return CODE_HEX;
    case "port":
      return "#1a1815";
    case "anchor":
      return "transparent";
    default:
      return INK_3;
  }
}

function minimapStroke(node: Node): string {
  switch (node.type) {
    case "status": {
      const id = (node.data as { status?: { id?: string } })?.status?.id ?? "";
      return statusHex(id);
    }
    case "tile":
      return INK_3;
    case "anchor":
      return "transparent";
    default:
      return "#1a1815";
  }
}
