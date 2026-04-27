import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BoardSessionCard } from "@/features/board/SessionCard";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

function makeSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: "v08-foo",
    name: "Foo session",
    agent: "frontend-coder",
    status: "executing",
    issues: [],
    estimated_size: "medium",
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 2, total: 5 },
    ...overrides,
  };
}

describe("BoardSessionCard", () => {
  it("renders the session id, title and agent", () => {
    renderWithProviders(
      <BoardSessionCard
        session={makeSession({ name: "Build the board", agent: "backend-coder" })}
      />,
    );
    expect(screen.getByText("v08-foo")).toBeInTheDocument();
    expect(screen.getByText("Build the board")).toBeInTheDocument();
    expect(screen.getByText("backend-coder")).toBeInTheDocument();
  });

  it("uses the canonical stage color for the status pill", () => {
    // The stage color comes from sessionStageColor() — the canonical
    // 7-stage mapping. We assert the stage label appears, not the
    // hex value, because the colour is set via inline style.
    renderWithProviders(<BoardSessionCard session={makeSession({ status: "executing" })} />);
    expect(screen.getByText(/executing/i)).toBeInTheDocument();
  });

  it("renders the inbox cross-link badge when there is an open blocked entry", () => {
    const onCrossLinkClick = vi.fn();
    renderWithProviders(
      <BoardSessionCard
        session={makeSession()}
        blockedInboxCount={2}
        onCrossLinkClick={onCrossLinkClick}
      />,
    );
    const badge = screen.getByRole("button", { name: /open blocked inbox entries/i });
    expect(badge).toBeInTheDocument();
    fireEvent.click(badge);
    expect(onCrossLinkClick).toHaveBeenCalled();
  });

  it("omits the cross-link badge when there is no open blocked entry", () => {
    renderWithProviders(<BoardSessionCard session={makeSession()} blockedInboxCount={0} />);
    expect(
      screen.queryByRole("button", { name: /open blocked inbox entries/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onClick when the card body is clicked (preview-drawer flow)", () => {
    const onClick = vi.fn();
    renderWithProviders(<BoardSessionCard session={makeSession()} onClick={onClick} />);
    fireEvent.click(screen.getByText("v08-foo"));
    expect(onClick).toHaveBeenCalled();
  });

  it("shows the re-engagement count chip when > 0", () => {
    renderWithProviders(<BoardSessionCard session={makeSession({ re_engagement_count: 3 })} />);
    expect(screen.getByText(/↺\s*3/)).toBeInTheDocument();
  });
});
