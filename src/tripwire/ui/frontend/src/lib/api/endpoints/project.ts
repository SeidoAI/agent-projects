import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface PhaseLogEntry {
  from: string;
  to: string;
  at: string;
  by: string | null;
}

/** Narrow view of `ProjectDetail` — extend as the UI needs more fields. */
export interface ProjectDetail {
  id: string;
  name: string;
  key_prefix: string;
  phase: string;
  phase_log?: PhaseLogEntry[];
}

export const projectApi = {
  get: (pid: string) => apiGet<ProjectDetail>(`/api/projects/${encodeURIComponent(pid)}`),
};

export function useProject(pid: string) {
  return useQuery({
    queryKey: queryKeys.project(pid),
    queryFn: () => projectApi.get(pid),
    staleTime: staleTime.default,
  });
}
