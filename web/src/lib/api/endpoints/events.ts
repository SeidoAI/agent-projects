import { useQuery } from "@tanstack/react-query";

import { ApiError, apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/**
 * Typed client for `/api/events` (Strand Y).
 *
 * The endpoint streams every "process event" (JIT prompt fires, validator
 * pass/fail, artifact rejections, PM reviews, status transitions). See
 * spec §2.2. As with workflow.ts, this client tolerates the endpoint
 * not being live yet — consumers see `data === undefined` and the
 * Dashboard centre column renders an empty state.
 */
export type ProcessEventKind =
  | "jit_prompt_fire"
  | "validator_pass"
  | "validator_fail"
  | "artifact_rejected"
  | "pm_review_opened"
  | "pm_review_closed"
  | "status_transition";

export interface EventResolution {
  kind: "ack" | "re_engaged" | "ignored" | "open" | string;
  at?: string;
  fix_commits?: string[];
  declared_no_findings?: boolean;
}

export interface ProcessEvent {
  id: string;
  kind: ProcessEventKind;
  fired_at: string;
  session_id: string;
  /* Discriminated by `kind`; we keep optional fields shared rather than
   * authoring a tagged union since the Dashboard only renders summary
   * fields and the Tripwire Log (S6) does the real interrogation. */
  jit_prompt_id?: string;
  validator_id?: string;
  artifact?: string;
  evidence?: string;
  rejected_by?: string;
  feedback_excerpt?: string;
  event?: string;
  blocks?: boolean;
  resolution?: EventResolution;
  // status_transition payload (core/session_store.py:_emit_status_transition).
  from_status?: string;
  to_status?: string;
}

export interface EventsResponse {
  events: ProcessEvent[];
  next_cursor: string | null;
}

export interface ListEventsParams {
  session_id?: string;
  kinds?: ProcessEventKind[];
  since?: string;
  limit?: number;
  cursor?: string;
}

function buildQuery(params: ListEventsParams): string {
  const qs = new URLSearchParams();
  if (params.session_id) qs.set("session_id", params.session_id);
  if (params.kinds?.length) {
    for (const k of params.kinds) qs.append("kind", k);
  }
  if (params.since) qs.set("since", params.since);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  if (params.cursor) qs.set("cursor", params.cursor);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const eventsApi = {
  list: (pid: string, params: ListEventsParams = {}) =>
    apiGet<EventsResponse>(`/api/projects/${encodeURIComponent(pid)}/events${buildQuery(params)}`),
  get: (pid: string, eventId: string) =>
    apiGet<ProcessEvent>(
      `/api/projects/${encodeURIComponent(pid)}/events/${encodeURIComponent(eventId)}`,
    ),
};

export function useWorkflowEvents(pid: string, params: ListEventsParams = {}) {
  return useQuery<EventsResponse>({
    queryKey: queryKeys.events(pid, params),
    queryFn: () => eventsApi.list(pid, params),
    staleTime: staleTime.default,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}

/**
 * Per-session view of the events feed — thin wrapper that always
 * pins `session_id`. Used by the Session Detail screen (S3) to
 * render the per-session filtered ProcessEvent feed in lieu of the
 * v0.9 turn timeline (deferred under Option C — see
 * `sessions/v08-session-detail/plan.md`).
 *
 * The cache key includes `session_id` plus any extra params, so a
 * second hook in the same project filtering different kinds gets a
 * separate cache entry.
 */
export function useSessionEvents(
  pid: string,
  sid: string,
  opts: Omit<ListEventsParams, "session_id"> = {},
) {
  return useWorkflowEvents(pid, { ...opts, session_id: sid });
}
