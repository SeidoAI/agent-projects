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
  WorkflowGraph,
  WorkflowRegistry,
  WorkflowRoute,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";
import { ActorEdge, CrossLinkEdge, ReturnEdge } from "./flowEdges";
import {
  buildUnifiedFlow,
  type BoundaryNodeData,
  type ChipNodeData,
  type DetourNodeData,
  type JitNodeData,
  type StatusNodeData,
  type TileNodeData,
  type WorkStepNodeData,
} from "./flowGraph";

import {
  AnchorNode,
  BoundaryTransitionNode,
  BranchDiamondNode,
  ChipNode,
  DetourTransitionNode,
  JitPromptNode,
  BandHeaderNode,
  CrossLinkEndpointNode,
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
  band: BandHeaderNode,
  crosslinkEndpoint: CrossLinkEndpointNode,
};

const EDGE_TYPES = {
  actor: ActorEdge,
  return: ReturnEdge,
  crosslink: CrossLinkEdge,
};

const DEFAULT_EDGE_OPTIONS = {
  type: "actor",
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
} as const;

const VIEWPORT_STORAGE_PREFIX = "tripwire:workflow-viewport:";

export type FlowSelection =
  | { kind: "status"; workflowId: string; status: WorkflowStatus }
  | { kind: "route"; workflowId: string; route: WorkflowRoute }
  | {
      kind: "work_step";
      workflowId: string;
      statusId: string;
      workStepId: string;
    }
  | {
      kind: "jit_prompt";
      workflowId: string;
      id: string;
      statusId: string;
    }
  | {
      kind: "artifact";
      workflowId: string;
      artifact: WorkflowArtifactRef;
      statusId: string;
      direction: "produces" | "consumes";
    };

export interface WorkflowFlowchartProps {
  /** All workflows in the project; rendered as stacked bands. */
  graph: WorkflowGraph;
  /** Which band to focus the viewport on initially / when this changes. */
  focusId?: string | null;
  registry?: WorkflowRegistry;
  gateMode?: "lock" | "diamond";
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
  graph,
  focusId,
  registry,
  gateMode = "diamond",
  onSelect,
}: WorkflowFlowchartProps) {
  const flow = useMemo(
    () => buildUnifiedFlow(graph, { gateMode }),
    [graph, gateMode],
  );
  // Stores the *namespaced* boundary node id of the currently-opened
  // gate panel, so it survives across bands without route-id collisions.
  const [openedBoundaryNodeId, setOpenedBoundaryNodeId] = useState<
    string | null
  >(null);
  const rf = useReactFlow();
  const nodesInitialized = useNodesInitialized();
  const lastInitForFocus = useRef<string | null>(null);

  // Initial viewport restore: only on the very first mount for this
  // project. Subsequent focusId changes always re-centre on the new band.
  const storageKey = `${VIEWPORT_STORAGE_PREFIX}${graph.project_id}`;
  const initialRestoreDone = useRef(false);
  useEffect(() => {
    if (!nodesInitialized || initialRestoreDone.current) return;
    initialRestoreDone.current = true;
    const raw =
      typeof window !== "undefined" ? sessionStorage.getItem(storageKey) : null;
    if (raw) {
      try {
        const v = JSON.parse(raw) as Viewport;
        rf.setViewport(v, { duration: 0 });
        lastInitForFocus.current = focusId ?? "__initial__";
        return;
      } catch {
        /* fall through to fitView */
      }
    }
    centreOnBand(rf, flow.bands, focusId ?? null, 200);
    lastInitForFocus.current = focusId ?? "__initial__";
  }, [nodesInitialized, focusId, storageKey, rf, flow.bands]);

  // On every subsequent focusId change, re-centre on the target band.
  // Decoupled from the initial-restore effect so the saved viewport
  // doesn't fight the focus update.
  useEffect(() => {
    if (!nodesInitialized || !initialRestoreDone.current) return;
    if (lastInitForFocus.current === focusId) return;
    centreOnBand(rf, flow.bands, focusId ?? null, 600);
    lastInitForFocus.current = focusId ?? "__initial__";
  }, [focusId, nodesInitialized, rf, flow.bands]);

  // Persist viewport on every settle.
  useOnViewportChange({
    onEnd: (v) => {
      if (typeof window !== "undefined") {
        sessionStorage.setItem(storageKey, JSON.stringify(v));
      }
    },
  });

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
    // Ensure the cross-link bus (at CROSSLINK_BUS_X = -120) is reachable
    // by panning. Bands sit at x ≥ 0; the bus lives in negative x.
    minX = Math.min(minX, -240);
    return [
      [minX - MARGIN, minY - MARGIN],
      [maxX + MARGIN, maxY + MARGIN],
    ];
  }, [flow.nodes]);

  // Walk the parent chain to find the band:<wf-id> ancestor — the
  // workflow id this node belongs to. Returns null if the node isn't
  // inside a band (shouldn't happen in unified mode).
  const workflowIdOf = (nodeId: string): string | null => {
    let cur: string | undefined = nodeId;
    const byId = new Map(flow.nodes.map((n) => [n.id, n]));
    for (let i = 0; i < 8 && cur; i += 1) {
      const n = byId.get(cur);
      if (!n) return null;
      if (n.type === "band") {
        const data = n.data as { workflowId?: string };
        return data.workflowId ?? null;
      }
      cur = n.parentId;
    }
    return null;
  };

  const handleNodeClick: NodeMouseHandler = (event, node) => {
    const target = event.target as HTMLElement;
    const gateBtn = target.closest('[data-testid^="workflow-gate-badge-"]');
    if (gateBtn) {
      // Find the ReactFlow node wrapper this badge lives in. Its
      // data-id attribute is the namespaced node id.
      const flowNodeEl = gateBtn.closest("[data-id]");
      const namespacedId = flowNodeEl?.getAttribute("data-id");
      if (namespacedId) {
        setOpenedBoundaryNodeId((prev) =>
          prev === namespacedId ? null : namespacedId,
        );
      }
      return;
    }
    // Cross-link endpoint dot: jump to the OTHER endpoint's specific
    // status region (tight close-up — fits the *region* not the whole
    // band, so the user lands looking AT the target node, not from
    // 30,000 ft up).
    if (node.type === "crosslinkEndpoint") {
      const d = node.data as {
        otherWorkflowId?: string;
        otherStatusId?: string;
      };
      if (d.otherWorkflowId && d.otherStatusId) {
        const targetRegionId = `band:${d.otherWorkflowId}:status:${d.otherStatusId}`;
        rf.fitView({
          nodes: [{ id: targetRegionId }],
          padding: 0.25,
          duration: 600,
          maxZoom: 1.0,
          minZoom: 0.6,
        });
      }
      return;
    }
    const toolbarBtn = target.closest("[data-toolbar-action]");
    if (toolbarBtn) {
      const action = toolbarBtn.getAttribute("data-toolbar-action");
      if (action === "zoom-to-status") {
        // node here is the status node — its own id is namespaced.
        rf.fitView({ nodes: [{ id: node.id }], padding: 0.2, duration: 600 });
        return;
      }
      if (action === "zoom-to-node") {
        rf.fitView({ nodes: [{ id: node.id }], padding: 0.4, duration: 500 });
        return;
      }
    }

    if (!onSelect) return;
    const wfId = workflowIdOf(node.id);
    if (!wfId) return;
    switch (node.type) {
      case "status": {
        const d = node.data as unknown as StatusNodeData;
        rf.fitView({ nodes: [{ id: node.id }], padding: 0.15, duration: 500 });
        onSelect({ kind: "status", workflowId: wfId, status: d.status });
        break;
      }
      case "workStep": {
        const d = node.data as unknown as WorkStepNodeData;
        onSelect({
          kind: "work_step",
          workflowId: wfId,
          statusId: d.statusId,
          workStepId: d.workStep.id,
        });
        break;
      }
      case "boundary":
      case "detour": {
        const d = node.data as unknown as BoundaryNodeData | DetourNodeData;
        onSelect({ kind: "route", workflowId: wfId, route: d.route });
        break;
      }
      case "chip": {
        const d = node.data as unknown as ChipNodeData;
        if (d.kind === "ref" && d.artifact) {
          onSelect({
            kind: "artifact",
            workflowId: wfId,
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
          workflowId: wfId,
          artifact: d.artifact,
          statusId: d.statusId,
          direction: "produces",
        });
        break;
      }
      case "jit": {
        const d = node.data as unknown as JitNodeData;
        onSelect({
          kind: "jit_prompt",
          workflowId: wfId,
          id: d.id,
          statusId: d.statusId,
        });
        break;
      }
    }
  };

  const openedRoute = useMemo<WorkflowRoute | null>(() => {
    if (!openedBoundaryNodeId) return null;
    const node = flow.nodes.find((n) => n.id === openedBoundaryNodeId);
    if (!node) return null;
    const data = node.data as unknown as BoundaryNodeData | DetourNodeData;
    return data?.route ?? null;
  }, [openedBoundaryNodeId, flow.nodes]);

  return (
    <div
      className="relative w-full"
      style={{ height: 760 }}
      data-testid="workflow-flowchart"
      data-project={graph.project_id}
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
        // Trackpad two-finger drag pans the canvas (the unified canvas
        // is the page now — there's no per-tab page scroll to compete
        // with). Pinch (which Macs deliver as ctrl+wheel) zooms.
        // zoomOnScroll left off so a non-pinch gesture never zooms.
        panOnScroll
        panOnScrollSpeed={0.7}
        zoomOnPinch
        zoomOnScroll={false}
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
          onClose={() => setOpenedBoundaryNodeId(null)}
        />
      )}
    </div>
  );
}

// Centre the viewport on a named band. We compute the centre + zoom from
// the band's known bounds (BandInfo) instead of fitView({nodes:[id]})
// because parent group nodes don't always report measured bounds in
// React Flow until they have visible children measured — which can race
// with the navigator click.
function centreOnBand(
  rf: ReturnType<typeof useReactFlow>,
  bands: Array<{
    workflowId: string;
    bandTop: number;
    width: number;
    height: number;
  }>,
  focusId: string | null,
  duration: number,
): void {
  const band = focusId
    ? bands.find((b) => b.workflowId === focusId)
    : bands[0];
  if (!band) return;
  // Aim for ~88% horizontal fit so the band has a little air. Pick the
  // smaller of width/height ratios so nothing clips.
  const PADDING = 0.12;
  const vw = window.innerWidth || 1280;
  const vh = (window.innerHeight || 800) - 200; // header + chrome estimate
  const zoom = Math.min(
    (vw * (1 - PADDING)) / Math.max(band.width, 1),
    (vh * (1 - PADDING)) / Math.max(band.height, 1),
    1.0,
  );
  rf.setCenter(band.width / 2, band.bandTop + band.height / 2, {
    zoom: Math.max(0.3, zoom),
    duration,
  });
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
