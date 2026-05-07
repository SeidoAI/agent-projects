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
  /**
   * v0.10.0 — opaque id of the workspace this project belongs to.
   * `null` when the project's `project.yaml` has no `workspace.path`
   * pointer or that pointer doesn't resolve to a registered workspace.
   * Used by the project switcher to group projects under workspace
   * headings.
   */
  workspace_id?: string | null;
  /**
   * v0.10.0 — `false` when project.yaml failed to load (schema
   * mismatch, parse error). Defaults to `true` for callers that
   * predate the field. Invalid projects are surfaced in the dropdown
   * with an `[INVALID]` stamp + the load_error tooltip and disabled
   * navigation, so the user can SEE the breakage instead of having
   * the project silently disappear from discovery.
   */
  valid?: boolean;
  load_error?: string | null;
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
