import { describe, expect, it } from "vitest";
import { computeStatusCounts } from "@/features/dashboard/hooks/useProjectStats";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";

function makeIssue(
  partial: Partial<IssueSummary> & Pick<IssueSummary, "id" | "status">,
): IssueSummary {
  return {
    title: partial.id,
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
    ...partial,
  };
}

describe("computeStatusCounts", () => {
  const enumDesc: EnumDescriptor = {
    name: "issue_status",
    values: [
      { value: "todo", label: "To do", color: "#888", description: null },
      { value: "doing", label: "Doing", color: "#0af", description: null },
      { value: "done", label: "Done", color: "#0f0", description: null },
    ],
  };

  it("returns an empty list when the status enum is missing", () => {
    expect(computeStatusCounts([makeIssue({ id: "X-1", status: "todo" })], undefined)).toEqual([]);
  });

  it("orders rows by enum order and fills zero counts for empty statuses", () => {
    const issues = [
      makeIssue({ id: "X-1", status: "todo" }),
      makeIssue({ id: "X-2", status: "todo" }),
      makeIssue({ id: "X-3", status: "done" }),
    ];
    const counts = computeStatusCounts(issues, enumDesc);
    expect(counts.map((c) => [c.value, c.count])).toEqual([
      ["todo", 2],
      ["doing", 0],
      ["done", 1],
    ]);
  });

  it("drops issues whose status is not in the enum", () => {
    const issues = [
      makeIssue({ id: "X-1", status: "todo" }),
      makeIssue({ id: "X-2", status: "archived" }),
    ];
    const counts = computeStatusCounts(issues, enumDesc);
    expect(counts.find((c) => c.value === "archived")).toBeUndefined();
    expect(counts.find((c) => c.value === "todo")?.count).toBe(1);
  });
});
