import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface NodeSource {
  repo: string;
  path: string;
  lines?: [number, number] | null;
  branch?: string | null;
  content_hash?: string | null;
}

export interface NodeLayout {
  x: number;
  y: number;
}

export interface NodeSummary {
  id: string;
  type: string;
  name: string;
  description: string | null;
  status: string;
  tags: string[];
  related: string[];
  ref_count: number;
  layout?: NodeLayout | null;
}

export interface NodeDetail extends NodeSummary {
  body: string;
  source: NodeSource | null;
  is_stale: boolean;
}

export type ReferrerKind = "issue" | "node" | "session";

export interface Referrer {
  id: string;
  kind: ReferrerKind;
}

export interface ReverseRefsResult {
  node_id: string;
  referrers: Referrer[];
}

export interface NodeFilters {
  type?: string;
  status?: string;
  stale?: boolean;
}

function encodeFilters(filters: NodeFilters | undefined): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.type) params.set("type", filters.type);
  if (filters.status) params.set("status", filters.status);
  if (filters.stale !== undefined) params.set("stale", String(filters.stale));
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const nodesApi = {
  list: (pid: string, filters?: NodeFilters) =>
    apiGet<NodeSummary[]>(
      `/api/projects/${encodeURIComponent(pid)}/nodes${encodeFilters(filters)}`,
    ),
  get: (pid: string, nid: string) =>
    apiGet<NodeDetail>(`/api/projects/${encodeURIComponent(pid)}/nodes/${encodeURIComponent(nid)}`),
  reverseRefs: (pid: string, nid: string) =>
    apiGet<ReverseRefsResult>(
      `/api/projects/${encodeURIComponent(pid)}/refs/reverse/${encodeURIComponent(nid)}`,
    ),
  // Concept Graph layout persistence moved to graphApi.updateConceptLayout
  // (PATCH /graph/concept/layout), batched into a single request that
  // writes the project-scoped sidecar instead of N node YAMLs.
};

export function useNode(pid: string, nid: string) {
  return useQuery({
    queryKey: queryKeys.node(pid, nid),
    queryFn: () => nodesApi.get(pid, nid),
    staleTime: staleTime.default,
    // Skip the fetch when no node is selected — callers like
    // GraphRail render a "no concept selected" placeholder and
    // pass `nid=""`, which would otherwise round-trip a 404.
    enabled: Boolean(nid),
  });
}

export function useNodes(pid: string, filters?: NodeFilters) {
  return useQuery({
    queryKey: filters ? [...queryKeys.nodes(pid), filters] : queryKeys.nodes(pid),
    queryFn: () => nodesApi.list(pid, filters),
    staleTime: staleTime.default,
  });
}

export function useReverseRefs(pid: string, nid: string) {
  return useQuery({
    queryKey: queryKeys.reverseRefs(pid, nid),
    queryFn: () => nodesApi.reverseRefs(pid, nid),
    staleTime: staleTime.default,
  });
}
