import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface TaskProgress {
  done: number;
  total: number;
}

export interface RepoBinding {
  repo: string;
  base_branch: string;
  branch: string | null;
  pr_number: number | null;
}

/** Mirrors `SessionSummary` from `tripwire.ui.services.session_service`. */
export interface SessionSummary {
  id: string;
  name: string;
  agent: string;
  status: string;
  issues: string[];
  estimated_size: string | null;
  blocked_by_sessions: string[];
  repos: RepoBinding[];
  current_state: string | null;
  re_engagement_count: number;
  task_progress: TaskProgress;
}

export interface SessionDetail extends SessionSummary {
  plan_md: string;
  key_files: string[];
  docs: string[];
  grouping_rationale: string | null;
  engagements: Record<string, unknown>[];
  artifact_status: Record<string, string>;
}

export const sessionsApi = {
  list: (pid: string, status?: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiGet<SessionSummary[]>(
      `/api/projects/${encodeURIComponent(pid)}/sessions${qs}`,
    );
  },
  get: (pid: string, sid: string) =>
    apiGet<SessionDetail>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}`,
    ),
};

export function useSessions(pid: string, status?: string) {
  return useQuery({
    queryKey: status ? [...queryKeys.sessions(pid), { status }] : queryKeys.sessions(pid),
    queryFn: () => sessionsApi.list(pid, status),
    staleTime: staleTime.default,
  });
}

export function useSession(pid: string, sid: string) {
  return useQuery({
    queryKey: queryKeys.session(pid, sid),
    queryFn: () => sessionsApi.get(pid, sid),
    staleTime: staleTime.default,
  });
}
