import { useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface PhaseLogEntry {
  from: string;
  to: string;
  at: string;
  by: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  key_prefix: string;
  dir?: string;
  phase: string;
  issue_count: number;
  node_count: number;
  session_count: number;
}

/** Narrow view of `ProjectDetail` — extend as the UI needs more fields. */
export interface ProjectDetail {
  id: string;
  name: string;
  key_prefix: string;
  dir?: string;
  phase: string;
  phase_log?: PhaseLogEntry[];
  status_transitions?: Record<string, string[]>;
  repos?: Record<string, { local?: string | null; github?: string | null }>;
  base_branch?: string;
  description?: string | null;
}

export const projectApi = {
  list: () => apiGet<ProjectSummary[]>("/api/projects"),
  get: (pid: string) => apiGet<ProjectDetail>(`/api/projects/${encodeURIComponent(pid)}`),
  find: (name: string, key_prefix: string) =>
    apiPost<ProjectSummary>("/api/projects/find", { name, key_prefix }),
};

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: projectApi.list,
    staleTime: staleTime.default,
  });
}

export function useProject(pid: string) {
  return useQuery({
    queryKey: queryKeys.project(pid),
    queryFn: () => projectApi.get(pid),
    staleTime: staleTime.default,
  });
}
