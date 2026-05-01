import { useQuery } from "@tanstack/react-query";

import { ApiError, apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/**
 * Typed client for `/api/projects/:pid/drift` (KUI-157 / I4).
 *
 * Returns the unified coherence score plus the per-class breakdown
 * and a chronological window of recent workflow_drift events for
 * the drill-down list. Wraps the substrate shipped in
 * `tripwire/core/drift.py`.
 */
export interface DriftBreakdown {
  stale_pins: number;
  unresolved_refs: number;
  stale_concepts: number;
  workflow_drift_events: number;
}

export interface WorkflowDriftEvent {
  event: "workflow_drift";
  at: string;
  kind?: string;
  // Free-form fields captured by the substrate emitter.
  [extra: string]: unknown;
}

export interface DriftReport {
  score: number;
  breakdown: DriftBreakdown;
  workflow_drift_events: WorkflowDriftEvent[];
}

export const driftApi = {
  get: (pid: string) =>
    apiGet<DriftReport>(`/api/projects/${encodeURIComponent(pid)}/drift`),
};

export function useDriftReport(pid: string) {
  return useQuery<DriftReport>({
    queryKey: queryKeys.drift(pid),
    queryFn: () => driftApi.get(pid),
    staleTime: staleTime.default,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}
