import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/lib/api/client";
import { type EnumDescriptor, enumsApi } from "@/lib/api/endpoints/enums";
import { type IssueFilterParams, type IssueSummary, issuesApi } from "@/lib/api/endpoints/issues";
import { queryKeys, staleTime } from "@/lib/api/queryKeys";

export function useIssues(pid: string, filters?: IssueFilterParams) {
  return useQuery({
    queryKey: filters ? queryKeys.issuesFiltered(pid, filters) : queryKeys.issues(pid),
    queryFn: () => issuesApi.list(pid, filters),
    staleTime: staleTime.default,
  });
}

export function useIssueStatusEnum(pid: string) {
  return useQuery<EnumDescriptor>({
    queryKey: queryKeys.enum(pid, "issue_status"),
    queryFn: () => enumsApi.get(pid, "issue_status"),
    staleTime: staleTime.enum,
  });
}

export interface UpdateStatusVariables {
  key: string;
  status: string;
}

interface Snapshot {
  queryKey: readonly unknown[];
  data: IssueSummary[];
}

interface MutationCtx {
  snapshots: Snapshot[];
}

/**
 * Optimistic PATCH for issue status. Every cache entry under the
 * `["issues", pid]` prefix — both `queryKeys.issues(pid)` and every
 * `queryKeys.issuesFiltered(pid, filters)` — gets the same optimistic
 * write and the same rollback on error. The dashboard deep-links the
 * board with `?status=` which will eventually drive the filtered key,
 * so this hook can't assume a single cache entry.
 */
export function useUpdateIssueStatus(pid: string) {
  const qc = useQueryClient();
  const prefix = ["issues", pid] as const;
  return useMutation<IssueSummary, ApiError, UpdateStatusVariables, MutationCtx>({
    mutationFn: ({ key, status }) => issuesApi.patch(pid, key, { status }),
    onMutate: async ({ key, status }) => {
      // Prefix-match cancel covers both the list key and any filtered
      // variant. Without this, a slower GET can clobber the optimistic
      // write on whichever view the user is looking at.
      await qc.cancelQueries({ queryKey: prefix });

      const snapshots: Snapshot[] = [];
      for (const query of qc.getQueryCache().findAll({ queryKey: prefix })) {
        const data = query.state.data as IssueSummary[] | undefined;
        if (!data) continue;
        snapshots.push({ queryKey: query.queryKey, data });
        qc.setQueryData<IssueSummary[]>(
          query.queryKey,
          data.map((i) => (i.id === key ? { ...i, status } : i)),
        );
      }
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => {
      if (!ctx) return;
      for (const s of ctx.snapshots) {
        qc.setQueryData(s.queryKey, s.data);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: prefix });
    },
  });
}
