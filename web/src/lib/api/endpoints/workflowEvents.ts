import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/**
 * Typed clients for the v0.9 workflow events log
 * (`/api/projects/{pid}/workflow-events` and `/workflow-stats`).
 *
 * Distinct from the v0.8 `endpoints/events.ts` client — that one
 * reads the FileEmitter's per-kind/per-session JSON; this one reads
 * the append-only events log substrate from KUI-123. Both coexist
 * for v0.9; the EventLog (KUI-155) and Process-Quality (KUI-156)
 * screens consume the v0.9 endpoints.
 */
export interface WorkflowEvent {
  ts: string;
  workflow: string;
  instance: string;
  status: string;
  event: string;
  details: Record<string, unknown>;
}

export interface WorkflowEventsPage {
  events: WorkflowEvent[];
  total: number;
}

export interface WorkflowEventsFilters {
  workflow?: string;
  instance?: string;
  status?: string;
  event?: string;
  limit?: number;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      usp.set(k, String(v));
    }
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const workflowEventsApi = {
  list: (pid: string, filters: WorkflowEventsFilters = {}) =>
    apiGet<WorkflowEventsPage>(
      `/api/projects/${encodeURIComponent(pid)}/workflow-events${buildQuery({ ...filters })}`,
    ),
  stats: (pid: string, opts: { workflow?: string; top_n?: number } = {}) =>
    apiGet<WorkflowStatsResponse>(
      `/api/projects/${encodeURIComponent(pid)}/workflow-stats${buildQuery({ ...opts })}`,
    ),
};

export interface WorkflowStatsResponse {
  total: number;
  by_kind: Record<string, number>;
  by_instance: Record<string, number>;
  top_rules: { id: string; count: number }[];
}

/**
 * Polling cadence for the events log. The events log is append-only
 * — a 5s poll keeps the EventLog UI fresh in the absence of WS
 * support for the new v0.9 events kind. The WS bridge is a future
 * follow-up; today's poll is the safe floor.
 */
export const WORKFLOW_EVENTS_REFETCH_MS = 5_000;

export function useWorkflowEvents(pid: string, filters: WorkflowEventsFilters = {}) {
  return useQuery<WorkflowEventsPage>({
    queryKey: queryKeys.workflowEvents(pid, filters),
    queryFn: () => workflowEventsApi.list(pid, filters),
    staleTime: staleTime.default,
    refetchInterval: WORKFLOW_EVENTS_REFETCH_MS,
  });
}

export function useWorkflowStats(pid: string, opts: { workflow?: string; top_n?: number } = {}) {
  return useQuery<WorkflowStatsResponse>({
    queryKey: queryKeys.workflowStats(pid, opts),
    queryFn: () => workflowEventsApi.stats(pid, opts),
    staleTime: staleTime.default,
    refetchInterval: WORKFLOW_EVENTS_REFETCH_MS,
  });
}
