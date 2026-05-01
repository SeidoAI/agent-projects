import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BoardIssueCard } from "@/features/board/IssueCard";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

function makeIssue(overrides: Partial<IssueSummary> = {}): IssueSummary {
  return {
    id: "KUI-1",
    title: "do the thing",
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

describe("BoardIssueCard", () => {
  it("renders id, title, executor and priority", () => {
    renderWithProviders(
      <BoardIssueCard issue={makeIssue({ priority: "high", executor: "human" })} />,
    );
    expect(screen.getByText("KUI-1")).toBeInTheDocument();
    expect(screen.getByText("do the thing")).toBeInTheDocument();
    expect(screen.getByText(/high/i)).toBeInTheDocument();
    expect(screen.getByText(/human/i)).toBeInTheDocument();
  });

  it("renders the inbox cross-link badge when there is an open blocked entry", () => {
    const onCrossLinkClick = vi.fn();
    renderWithProviders(
      <BoardIssueCard
        issue={makeIssue()}
        blockedInboxCount={1}
        onCrossLinkClick={onCrossLinkClick}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /open blocked inbox entries/i }));
    expect(onCrossLinkClick).toHaveBeenCalled();
  });

  it("calls onClick when the card body is clicked", () => {
    const onClick = vi.fn();
    renderWithProviders(<BoardIssueCard issue={makeIssue()} onClick={onClick} />);
    fireEvent.click(screen.getByText("KUI-1"));
    expect(onClick).toHaveBeenCalled();
  });

  it("shows the blocked icon when is_blocked is true", () => {
    renderWithProviders(<BoardIssueCard issue={makeIssue({ is_blocked: true })} />);
    expect(screen.getByLabelText(/^blocked$/i)).toBeInTheDocument();
  });
});
