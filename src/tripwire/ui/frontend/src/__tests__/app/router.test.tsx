import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Placeholder } from "@/app/Placeholder";
import { ProjectShell } from "@/app/ProjectShell";
import { __resetProjectWebSocketsForTests } from "@/lib/realtime/useProjectWebSocket";

// Avoid opening a real WebSocket when ProjectShell mounts — the router
// tests only care about the layout, not the live data path.
vi.mock("@/lib/realtime/websocketClient", () => ({
  createWebSocketClient: () => ({
    close: vi.fn(),
    getStatus: () => "connecting",
  }),
}));

afterEach(() => {
  cleanup();
  __resetProjectWebSocketsForTests();
});

function renderRoute(path: string) {
  const routes = [
    { path: "/projects", element: <Placeholder name="ProjectList" /> },
    {
      path: "/p/:projectId",
      element: <ProjectShell />,
      children: [
        { index: true, element: <Navigate to="board" replace /> },
        { path: "board", element: <Placeholder name="KanbanBoard" /> },
        { path: "graph", element: <Placeholder name="ConceptGraph" /> },
        { path: "sessions", element: <Placeholder name="SessionList" /> },
        { path: "workflow", element: <Placeholder name="WorkflowMap" /> },
        { path: "tripwires", element: <Placeholder name="TripwireLog" /> },
      ],
    },
  ];
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("Router", () => {
  it("renders ProjectList placeholder at /projects", () => {
    renderRoute("/projects");
    expect(screen.getByText("ProjectList")).toBeDefined();
    expect(screen.getByText("Coming in a later issue.")).toBeDefined();
  });

  it("renders ProjectShell with breadcrumb project id at /p/:projectId/board", () => {
    renderRoute("/p/proj-1/board");
    // ScreenShell breadcrumb + project chip both render the project id
    // ("Workspace / proj-1" + the chip in the side rail).
    expect(screen.getAllByText("proj-1").length).toBeGreaterThan(0);
    // Board placeholder renders inside the outlet
    expect(screen.getByText("KanbanBoard")).toBeDefined();
  });

  it("renders the cream-palette nav items in the side rail", () => {
    renderRoute("/p/proj-1/board");
    // Lowercase nav per spec §3.1 C0.3.
    expect(screen.getByRole("link", { name: /overview/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /board/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /workflow/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /concepts/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /sessions/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /tripwires/ })).toBeDefined();
  });

  it("renders the workflow placeholder at /workflow", () => {
    renderRoute("/p/proj-1/workflow");
    expect(screen.getByText("WorkflowMap")).toBeDefined();
  });

  it("renders the tripwire log placeholder at /tripwires", () => {
    renderRoute("/p/proj-1/tripwires");
    expect(screen.getByText("TripwireLog")).toBeDefined();
  });
});
