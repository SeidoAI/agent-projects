import { apiGet } from "../client";

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

export const sessionsApi = {
  list: (pid: string, status?: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiGet<SessionSummary[]>(`/api/projects/${encodeURIComponent(pid)}/sessions${qs}`);
  },
};
