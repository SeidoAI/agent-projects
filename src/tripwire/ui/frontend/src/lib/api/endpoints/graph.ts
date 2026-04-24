import { apiGet } from "../client";

export type GraphKind = "deps" | "concept";

export interface ReactFlowPosition {
  x: number;
  y: number;
}

/** Mirrors `ReactFlowNode` from `tripwire.ui.services.graph_service`. */
export interface ReactFlowNode {
  id: string;
  type: string;
  position: ReactFlowPosition;
  data: Record<string, unknown>;
}

export interface ReactFlowEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  data: Record<string, unknown>;
}

export interface GraphMeta {
  kind: GraphKind;
  focus: string | null;
  upstream: boolean;
  downstream: boolean;
  depth: number | null;
  node_count: number;
  edge_count: number;
  orphans: string[];
}

export interface ReactFlowGraph {
  nodes: ReactFlowNode[];
  edges: ReactFlowEdge[];
  meta: GraphMeta;
}

export interface ConceptGraphParams {
  focus?: string;
  upstream?: boolean;
  downstream?: boolean;
}

function buildConceptQuery(params?: ConceptGraphParams): string {
  if (!params) return "";
  const qs = new URLSearchParams();
  if (params.focus) qs.set("focus", params.focus);
  if (params.upstream) qs.set("upstream", "true");
  if (params.downstream) qs.set("downstream", "true");
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const graphApi = {
  concept: (pid: string, params?: ConceptGraphParams) =>
    apiGet<ReactFlowGraph>(
      `/api/projects/${encodeURIComponent(pid)}/graph/concept${buildConceptQuery(params)}`,
    ),
};
