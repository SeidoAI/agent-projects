import { describe, expect, it } from "vitest";

import { OFF_TRACK_STAGE_ID, UNASSIGNED_STAGE_ID } from "@/components/ui/session-stage-row";
import { bucketByStage } from "@/features/dashboard/hooks/useProjectStats";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";

function sess(id: string, status: string, issues: string[] = []): SessionSummary {
  return {
    id,
    name: id,
    agent: "test-agent",
    status,
    issues,
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    cost_usd: 0,
  };
}

function issue(id: string): IssueSummary {
  return {
    id,
    title: id,
    status: "todo",
    priority: "medium",
    executor: "ai",
    verifier: "required",
    kind: null,
    agent: null,
    labels: [],
    parent: null,
    repo: null,
    blocked_by: [],
    is_blocked: false,
    is_epic: false,
    created_at: null,
    updated_at: null,
  };
}

describe("bucketByStage", () => {
  it("counts a session under its canonical stage", () => {
    const buckets = bucketByStage([sess("s1", "executing")], []);
    expect(buckets.executing?.sessionCount).toBe(1);
    expect(buckets.queued?.sessionCount).toBe(0);
  });

  it("collapses richer backend states (active, waiting_for_*) onto executing", () => {
    // The backend session_status enum has 14 values; the 7-card row
    // collapses the "still working" cluster into `executing`. Without
    // the canonicalisation, these would scatter across raw-string
    // buckets and the row would under-count.
    const buckets = bucketByStage(
      [
        sess("s1", "active"),
        sess("s2", "waiting_for_ci"),
        sess("s3", "waiting_for_review"),
        sess("s4", "executing"),
      ],
      [],
    );
    expect(buckets.executing?.sessionCount).toBe(4);
  });

  it("counts off-track sessions (failed/paused/abandoned) under off_track", () => {
    // Off-track sessions are NOT skipped — they surface in the
    // SessionStageRow off-track card with alert chrome. The previous
    // docstring incorrectly claimed they were excluded; this test
    // locks the actual (and intended) behaviour against future drift.
    const buckets = bucketByStage(
      [sess("s1", "failed"), sess("s2", "paused"), sess("s3", "abandoned")],
      [],
    );
    expect(buckets[OFF_TRACK_STAGE_ID]?.sessionCount).toBe(3);
  });

  it("places issues in the same stage as their parent session", () => {
    // The session stage is the source of truth for issue placement —
    // an issue assigned to an in_review session counts under
    // in_review even if the issue's own status disagrees.
    const buckets = bucketByStage(
      [sess("s1", "in_review", ["I-1", "I-2"])],
      [issue("I-1"), issue("I-2")],
    );
    expect(buckets.in_review?.issueCount).toBe(2);
    expect(buckets[UNASSIGNED_STAGE_ID]?.issueCount).toBe(0);
  });

  it("places issues with no session into the unassigned bucket", () => {
    const buckets = bucketByStage([], [issue("I-orphan")]);
    expect(buckets[UNASSIGNED_STAGE_ID]?.issueCount).toBe(1);
  });

  it("skips sessions with an unknown/unmapped status (defensive)", () => {
    // If a future status enum value lands without a SESSION_STAGES
    // entry, the bucketing should not throw — just drop the session.
    // Issues attached to that session fall through to unassigned.
    const buckets = bucketByStage([sess("s1", "totally-unknown-status", ["I-1"])], [issue("I-1")]);
    // No off-by-one in any bucket.
    for (const stage of Object.values(buckets)) {
      expect(stage.sessionCount).toBe(0);
    }
    // Issue lands in unassigned because the session's stage didn't
    // resolve.
    expect(buckets[UNASSIGNED_STAGE_ID]?.issueCount).toBe(1);
  });
});
