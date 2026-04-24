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

interface MutationCtx {
  previous: IssueSummary[] | undefined;
}

/**
 * Optimistic PATCH for issue status. The mutation:
 *   1. cancels in-flight list fetches so the optimistic write isn't
 *      clobbered by a slower GET,
 *   2. snapshots the current list into `context.previous`,
 *   3. writes the new status into the cache immediately,
 *   4. on error, restores the snapshot (caller surfaces the toast),
 *   5. on success/error alike, invalidates `issues(pid)` so the next
 *      render reflects the authoritative server state.
 */
export function useUpdateIssueStatus(pid: string) {
  const qc = useQueryClient();
  return useMutation<IssueSummary, ApiError, UpdateStatusVariables, MutationCtx>({
    mutationFn: ({ key, status }) => issuesApi.patch(pid, key, { status }),
    onMutate: async ({ key, status }) => {
      await qc.cancelQueries({ queryKey: queryKeys.issues(pid) });
      const previous = qc.getQueryData<IssueSummary[]>(queryKeys.issues(pid));
      if (previous) {
        qc.setQueryData<IssueSummary[]>(
          queryKeys.issues(pid),
          previous.map((i) => (i.id === key ? { ...i, status } : i)),
        );
      }
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(queryKeys.issues(pid), ctx.previous);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.issues(pid) });
    },
  });
}
