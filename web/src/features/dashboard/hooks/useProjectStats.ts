import { useQuery } from "@tanstack/react-query";

import {
  SESSION_STAGES,
  type StageBucket,
  sessionStageId,
  UNASSIGNED_STAGE_ID,
} from "@/components/ui/session-stage-row";
import { type IssueSummary, issuesApi } from "@/lib/api/endpoints/issues";
import { type SessionSummary, sessionsApi } from "@/lib/api/endpoints/sessions";
import { queryKeys, staleTime } from "@/lib/api/queryKeys";

export function useIssuesList(pid: string) {
  return useQuery({
    queryKey: queryKeys.issues(pid),
    queryFn: () => issuesApi.list(pid),
    staleTime: staleTime.default,
  });
}

export function useSessionsList(pid: string) {
  return useQuery({
    queryKey: queryKeys.sessions(pid),
    queryFn: () => sessionsApi.list(pid),
    staleTime: staleTime.default,
  });
}

/**
 * Bucket sessions + issues by canonical lifecycle stage for the
 * top-of-dashboard SessionStageRow.
 *
 * The session stage is the source of truth for issue placement: every
 * issue assigned to a session counts under that session's stage,
 * regardless of the issue's own status. Drift cases (session
 * `in_review` with issues `done`) count under the session stage —
 * the drift itself is a separate signal handled by the inbox.
 *
 * Issues with no session land in the `unassigned` bucket. Off-track
 * sessions (failed/paused/abandoned) collapse to the canonical
 * `off_track` stage and surface in the SessionStageRow's off-track
 * card with alert chrome — they are NOT skipped.
 */
export function bucketByStage(
  sessions: SessionSummary[],
  issues: IssueSummary[],
): Record<string, StageBucket> {
  const buckets: Record<string, StageBucket> = {
    [UNASSIGNED_STAGE_ID]: { sessionCount: 0, issueCount: 0 },
  };
  for (const stage of SESSION_STAGES) {
    buckets[stage.id] = { sessionCount: 0, issueCount: 0 };
  }
  const bump = (stageId: string, key: keyof StageBucket) => {
    const bucket = buckets[stageId];
    if (bucket) bucket[key] += 1;
  };
  const issueToSessionStage = new Map<string, string>();
  for (const session of sessions) {
    const stageId = sessionStageId(session.status);
    if (!stageId) continue; // unmapped status — skip (no canonical stage)
    bump(stageId, "sessionCount");
    for (const issueId of session.issues) {
      issueToSessionStage.set(issueId, stageId);
    }
  }
  for (const issue of issues) {
    const stageId = issueToSessionStage.get(issue.id);
    bump(stageId ?? UNASSIGNED_STAGE_ID, "issueCount");
  }
  return buckets;
}

export interface ProjectStats {
  totalIssues: number;
  sessions: SessionSummary[];
  issues: IssueSummary[];
  buckets: Record<string, StageBucket>;
  isLoading: boolean;
  isError: boolean;
}

export function useProjectStats(pid: string): ProjectStats {
  const issues = useIssuesList(pid);
  const sessions = useSessionsList(pid);

  const buckets = bucketByStage(sessions.data ?? [], issues.data ?? []);

  return {
    totalIssues: issues.data?.length ?? 0,
    sessions: sessions.data ?? [],
    issues: issues.data ?? [],
    buckets,
    isLoading: issues.isLoading || sessions.isLoading,
    isError: issues.isError || sessions.isError,
  };
}
