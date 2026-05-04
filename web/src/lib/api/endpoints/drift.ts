import { useQuery } from "@tanstack/react-query";

import { ApiError, apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/**
 * Typed client for `/api/projects/:pid/drift` (KUI-157 / I4).
 *
 * Returns the unified coherence score plus the per-class breakdown
 * and active workflow drift findings for the drill-down list. Wraps
 * the substrate shipped in `tripwire/core/drift.py`.
 */
export interface DriftBreakdown {
  stale_pins: number;
  unresolved_refs: number;
  stale_concepts: number;
  workflow_drift_findings: number;
}

export interface WorkflowDriftFinding {
  code: string;
  workflow: string;
  instance: string;
  status: string | null;
  severity: "error" | "warning";
  message: string;
}

export interface DriftReport {
  score: number;
  breakdown: DriftBreakdown;
  workflow_drift_findings: WorkflowDriftFinding[];
}

export const driftApi = {
  get: (pid: string) => apiGet<DriftReport>(`/api/projects/${encodeURIComponent(pid)}/drift`),
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
