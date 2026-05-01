import { apiGet, apiPatch } from "../client";

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

/** Single Concept Graph node position. Mirrors the backend `LayoutEntry`
 *  Pydantic model in `routes/graph.py`. */
export interface ConceptLayoutEntry {
  x: number;
  y: number;
}

/** Response payload for `PATCH /graph/concept/layout`. */
export interface ConceptLayoutResponse {
  layouts: Record<string, ConceptLayoutEntry>;
}

export const graphApi = {
  concept: (pid: string, params?: ConceptGraphParams) =>
    apiGet<ReactFlowGraph>(
      `/api/projects/${encodeURIComponent(pid)}/graph/concept${buildConceptQuery(params)}`,
    ),

  /** Merge a batch of `(node id → {x, y})` into the project's
   *  `.tripwire/concept-layout.json` sidecar. One HTTP call per
   *  debounced flush, instead of N per-node PATCHes — keeps layout
   *  edits out of content YAML and out of the file watcher's
   *  classifier. */
  updateConceptLayout: (pid: string, layouts: Record<string, ConceptLayoutEntry>) =>
    apiPatch<ConceptLayoutResponse>(
      `/api/projects/${encodeURIComponent(pid)}/graph/concept/layout`,
      layouts,
    ),
};
