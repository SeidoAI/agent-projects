import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { IssuesView } from "@/features/board/IssuesView";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

function makeIssue(overrides: Partial<IssueSummary>): IssueSummary {
  return {
    id: "X",
    title: "x",
    status: "backlog",
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
    created_at: "2026-04-20T12:00:00Z",
    updated_at: "2026-04-20T12:00:00Z",
    ...overrides,
  };
}

const STATUS_VALUES = [
  { value: "backlog", label: "Backlog", color: null, description: null },
  { value: "todo", label: "To Do", color: null, description: null },
  { value: "in_progress", label: "In Progress", color: null, description: null },
  { value: "in_review", label: "In Review", color: null, description: null },
  { value: "verified", label: "Verified", color: null, description: null },
  { value: "done", label: "Done", color: null, description: null },
];

describe("IssuesView", () => {
  it("renders one column per status enum value", () => {
    renderWithProviders(
      <IssuesView
        projectId="p1"
        issues={[]}
        statusValues={STATUS_VALUES}
        blockedInbox={{ bySession: new Map(), byIssue: new Map(), ready: true }}
        onCardClick={() => {}}
        onCrossLinkClick={() => {}}
      />,
    );
    for (const s of STATUS_VALUES) {
      expect(screen.getByRole("region", { name: new RegExp(s.label, "i") })).toBeInTheDocument();
    }
  });

  it("places issues into their column by status", () => {
    renderWithProviders(
      <IssuesView
        projectId="p1"
        issues={[
          makeIssue({ id: "A", status: "backlog" }),
          makeIssue({ id: "B", status: "in_review" }),
        ]}
        statusValues={STATUS_VALUES}
        blockedInbox={{ bySession: new Map(), byIssue: new Map(), ready: true }}
        onCardClick={() => {}}
        onCrossLinkClick={() => {}}
      />,
    );
    const backlog = screen.getByRole("region", { name: /backlog/i });
    expect(within(backlog).getByText("A")).toBeInTheDocument();
    const review = screen.getByRole("region", { name: /in review/i });
    expect(within(review).getByText("B")).toBeInTheDocument();
  });
});
