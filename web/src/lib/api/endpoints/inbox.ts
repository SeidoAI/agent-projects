import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

/** Reference shapes inside an inbox entry. The backend serialises
 *  each ref as a dict with the type key (`issue`, `session`, etc.)
 *  present — the frontend switches on key presence to render. */
export type InboxReference =
  | { issue: string }
  | { epic: string }
  | { session: string }
  | { node: string; version?: string }
  | { artifact: { session: string; file: string } }
  | { comment: { issue: string; id: string } }
  | { pr: string };

/** Mirrors `InboxItem` from `tripwire.ui.services.inbox_service`. */
export interface InboxItem {
  id: string;
  bucket: "blocked" | "fyi";
  title: string;
  body: string;
  author: string;
  created_at: string;
  references: InboxReference[];
  escalation_reason: string | null;
  resolved: boolean;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface InboxFilters {
  bucket?: "blocked" | "fyi";
  resolved?: boolean;
}

function buildQuery(filters?: InboxFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.bucket) params.set("bucket", filters.bucket);
  if (filters.resolved !== undefined) params.set("resolved", String(filters.resolved));
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const inboxApi = {
  list: (pid: string, filters?: InboxFilters) =>
    apiGet<InboxItem[]>(`/api/projects/${encodeURIComponent(pid)}/inbox${buildQuery(filters)}`),
  get: (pid: string, id: string) =>
    apiGet<InboxItem>(`/api/projects/${encodeURIComponent(pid)}/inbox/${encodeURIComponent(id)}`),
  resolve: (pid: string, id: string, resolvedBy?: string) =>
    apiPost<InboxItem>(
      `/api/projects/${encodeURIComponent(pid)}/inbox/${encodeURIComponent(id)}/resolve`,
      { resolved_by: resolvedBy ?? null },
    ),
};

export function useInbox(pid: string, filters?: InboxFilters) {
  return useQuery({
    queryKey: filters ? queryKeys.inboxFiltered(pid, filters) : queryKeys.inbox(pid),
    queryFn: () => inboxApi.list(pid, filters),
    staleTime: staleTime.default,
  });
}

export function useInboxItem(pid: string, id: string) {
  return useQuery({
    queryKey: queryKeys.inboxItem(pid, id),
    queryFn: () => inboxApi.get(pid, id),
    staleTime: staleTime.default,
    // Skip the fetch when the drawer is closed (id="") — keeps the
    // hook order stable while avoiding a 404 round-trip.
    enabled: Boolean(id),
  });
}

/** Resolve an inbox entry. On success every inbox query under
 *  ``["inbox", pid, ...]`` is invalidated — the list query refetches
 *  and removes the item; any open per-item drawer refetches and
 *  reflects the new ``resolved: true``. We deliberately do NOT
 *  ``setQueryData`` for the item cache: TanStack's prefix-match
 *  invalidation would mark our just-set value stale immediately,
 *  defeating the optimistic write. One source of truth — the
 *  invalidate alone — keeps the flow simple and correct. */
export function useResolveInbox(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, resolvedBy }: { id: string; resolvedBy?: string }) =>
      inboxApi.resolve(pid, id, resolvedBy),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.inbox(pid) });
    },
  });
}
