import { useQuery } from "@tanstack/react-query";

import { type EnumDescriptor, enumsApi } from "@/lib/api/endpoints/enums";
import { type IssueSummary, issuesApi } from "@/lib/api/endpoints/issues";
import { type SessionSummary, sessionsApi } from "@/lib/api/endpoints/sessions";
import { queryKeys, staleTime } from "@/lib/api/queryKeys";

export interface StatusCount {
  value: string;
  label: string;
  color: string | null;
  count: number;
}

/**
 * Aggregate status → count rows for the dashboard, ordered by the
 * project's `issue_status` enum. Values absent from the enum are
 * dropped rather than appended — the enum is the source of truth for
 * what columns the UI shows, and an unexpected value almost always
 * means a typo in an issue file that validation will surface.
 */
export function computeStatusCounts(
  issues: IssueSummary[],
  statusEnum: EnumDescriptor | undefined,
): StatusCount[] {
  if (!statusEnum) return [];
  const counts = new Map<string, number>();
  for (const issue of issues) {
    counts.set(issue.status, (counts.get(issue.status) ?? 0) + 1);
  }
  return statusEnum.values.map((v) => ({
    value: v.value,
    label: v.label,
    color: v.color,
    count: counts.get(v.value) ?? 0,
  }));
}

export function useIssuesList(pid: string) {
  return useQuery({
    queryKey: queryKeys.issues(pid),
    queryFn: () => issuesApi.list(pid),
    staleTime: staleTime.default,
  });
}

export function useIssueStatusEnum(pid: string) {
  return useQuery({
    queryKey: queryKeys.enum(pid, "issue_status"),
    queryFn: () => enumsApi.get(pid, "issue_status"),
    staleTime: staleTime.enum,
  });
}

export function useSessionsList(pid: string) {
  return useQuery({
    queryKey: queryKeys.sessions(pid),
    queryFn: () => sessionsApi.list(pid),
    staleTime: staleTime.default,
  });
}

export interface ProjectStats {
  statusCounts: StatusCount[];
  totalIssues: number;
  recentSessions: SessionSummary[];
  isLoading: boolean;
  isError: boolean;
}

export function useProjectStats(pid: string): ProjectStats {
  const issues = useIssuesList(pid);
  const statusEnum = useIssueStatusEnum(pid);
  const sessions = useSessionsList(pid);

  const statusCounts = computeStatusCounts(issues.data ?? [], statusEnum.data);

  // The sessions endpoint returns them in on-disk order — no
  // guaranteed sort. For "recent" we leave the order as the backend
  // gave us and slice the top 5; upgrading to a real "last-updated"
  // sort needs the backend to surface that field (it doesn't today).
  const recentSessions = (sessions.data ?? []).slice(0, 5);

  return {
    statusCounts,
    totalIssues: issues.data?.length ?? 0,
    recentSessions,
    isLoading: issues.isLoading || statusEnum.isLoading || sessions.isLoading,
    isError: issues.isError || statusEnum.isError || sessions.isError,
  };
}
