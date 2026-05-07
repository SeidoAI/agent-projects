import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CriticalPathSpine } from "@/components/ui/critical-path-spine";
import type { CriticalPathResult } from "@/features/dashboard/hooks/useCriticalPath";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";

afterEach(cleanup);

function fakeSession(id: string): SessionSummary {
  return {
    id,
    name: id,
    agent: "claude-sonnet-4",
    status: "executing",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    cost_usd: 0,
  };
}

function chainResult(length: number): CriticalPathResult {
  const chain = Array.from({ length }, (_, i) => fakeSession(`s-${i}`));
  return {
    chain,
    fanout: length,
    tied: false,
    inFlightCount: length,
    directUnlocks: Object.fromEntries(chain.map((s) => [s.id, 0])),
  };
}

describe("CriticalPathSpine wrap gap", () => {
  it("uses gap-y-14 on the chain ol so wrapped rows clear the 48px upward arcs", () => {
    // Long enough that any reasonable viewport wraps the chain. The
    // gap class is what guarantees no overlap regardless of where
    // the wrap lands.
    const { container } = render(
      <CriticalPathSpine
        result={chainResult(20)}
        selectedBlocker={null}
        onSelectBlocker={() => {}}
      />,
    );
    const ol = container.querySelector("ol");
    expect(ol).not.toBeNull();
    expect(ol!.className).toContain("gap-y-14");
    // Sanity: the old (too-tight) gap shouldn't survive a refactor.
    expect(ol!.className).not.toContain("gap-y-3 ");
  });
});
