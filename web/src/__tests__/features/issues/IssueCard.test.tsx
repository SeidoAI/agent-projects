import { DndContext } from "@dnd-kit/core";
import { cleanup, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { IssueCard } from "@/features/issues/IssueCard";
import { makeIssueSummary } from "../../mocks/fixtures";
import { renderWithProviders } from "../../test-utils";

/**
 * IssueCard mostly renders branches: epic vs not, blocked vs not,
 * priority style table lookup, agent line, refCount badge, transform
 * style. The KanbanBoard tests only ever render the default-shaped
 * issue (medium priority, not epic, not blocked, no agent, no
 * refCount) — so half the branches go unexercised. This file walks
 * each one explicitly.
 */
function withDnd(target: ReactNode) {
  return <DndContext>{target}</DndContext>;
}

afterEach(() => {
  cleanup();
});

describe("IssueCard", () => {
  it("applies epic styling when is_epic is true", () => {
    renderWithProviders(<IssueCard issue={makeIssueSummary({ id: "X-1", is_epic: true })} />, {
      initialPath: "/p/p1/board",
      routePath: "/p/:projectId/board",
      wrap: withDnd,
    });
    const card = screen.getByTestId("issue-card-X-1");
    expect(card.className).toMatch(/border-dashed/);
  });

  it("renders the blocked indicator when is_blocked is true", () => {
    renderWithProviders(<IssueCard issue={makeIssueSummary({ id: "X-1", is_blocked: true })} />, {
      initialPath: "/p/p1/board",
      routePath: "/p/:projectId/board",
      wrap: withDnd,
    });
    expect(screen.getByRole("img", { name: "Blocked" })).toBeInTheDocument();
  });

  it("renders the agent name when present", () => {
    renderWithProviders(
      <IssueCard issue={makeIssueSummary({ id: "X-1", agent: "frontend-coder" })} />,
      {
        initialPath: "/p/p1/board",
        routePath: "/p/:projectId/board",
        wrap: withDnd,
      },
    );
    expect(screen.getByText("frontend-coder")).toBeInTheDocument();
  });

  it("renders the refCount badge when refCount > 0", () => {
    renderWithProviders(<IssueCard issue={makeIssueSummary({ id: "X-1" })} refCount={3} />, {
      initialPath: "/p/p1/board",
      routePath: "/p/:projectId/board",
      wrap: withDnd,
    });
    expect(screen.getByRole("img", { name: "3 refs" })).toBeInTheDocument();
  });

  it("hides the refCount badge when refCount is zero", () => {
    renderWithProviders(<IssueCard issue={makeIssueSummary({ id: "X-1" })} refCount={0} />, {
      initialPath: "/p/p1/board",
      routePath: "/p/:projectId/board",
      wrap: withDnd,
    });
    expect(screen.queryByRole("img", { name: /refs/ })).toBeNull();
  });

  it.each([
    ["critical", "rule"],
    ["high", "tripwire"],
    ["medium", "default"],
    ["low", "default"],
  ])("applies the priority tone for %s", (priority, expectedTone) => {
    renderWithProviders(<IssueCard issue={makeIssueSummary({ id: "X-1", priority })} />, {
      initialPath: "/p/p1/board",
      routePath: "/p/:projectId/board",
      wrap: withDnd,
    });
    expect(screen.getByText(priority)).toHaveAttribute("data-tone", expectedTone);
  });

  it("falls back to default tone for an unknown priority value", () => {
    renderWithProviders(
      <IssueCard issue={makeIssueSummary({ id: "X-1", priority: "made-up" })} />,
      {
        initialPath: "/p/p1/board",
        routePath: "/p/:projectId/board",
        wrap: withDnd,
      },
    );
    expect(screen.getByText("made-up")).toHaveAttribute("data-tone", "default");
  });
});
