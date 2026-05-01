import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "../client";
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
  /** Running cost in USD, computed by walking the session's runtime log.
   *  `0` for sessions that have never spawned. Surfaced by the Live
   *  Monitor cost ticker and the dashboard cost columns. */
  cost_usd: number;
}

/** One launch of a coding-agent container against a session. See
 *  `[[engagement-primitive]]`. The full set of fields is documented
 *  on the node; this interface mirrors what the backend serialises
 *  via `runtime_state.engagements` on `session.yaml`. Optional fields
 *  reflect engagements that are still in flight (no `ended_at` /
 *  `outcome` yet) or older entries written before a field existed. */
export interface Engagement {
  engagement_id?: string;
  started_at: string;
  ended_at?: string | null;
  trigger?: "spawn" | "re-engagement" | "resume" | "human-resume" | string;
  outcome?: "success" | "paused" | "failed" | "abandoned" | string | null;
  agent_state?: string | null;
  cost_usd?: number | null;
  commit_sha?: string | null;
}

export interface SessionDetail extends SessionSummary {
  plan_md: string;
  key_files: string[];
  docs: string[];
  grouping_rationale: string | null;
  engagements: Engagement[];
  artifact_status: Record<string, string>;
}

/** Mutation: `POST /api/projects/{pid}/sessions/{sid}/pause` —
 *  KUI-107 INTERVENE. Mirrors the CLI ``tripwire session pause``
 *  endpoint exposed over HTTP. */
export interface PauseSessionResult {
  session_id: string;
  status: string;
  changed_at: string;
}

export const sessionsApi = {
  list: (pid: string, status?: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiGet<SessionSummary[]>(`/api/projects/${encodeURIComponent(pid)}/sessions${qs}`);
  },
  get: (pid: string, sid: string) =>
    apiGet<SessionDetail>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}`,
    ),
  pause: (pid: string, sid: string) =>
    apiPost<PauseSessionResult>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}/pause`,
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

/** Mutation: pause an executing session via `POST .../pause`. The
 *  cache for `useSession(pid, sid)` is invalidated on success so the
 *  Live Monitor's status header reads `paused` immediately and any
 *  list views refresh their stage bucket counts. */
export function usePauseSession(pid: string, sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => sessionsApi.pause(pid, sid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.session(pid, sid) });
      qc.invalidateQueries({ queryKey: queryKeys.sessions(pid) });
    },
  });
}
