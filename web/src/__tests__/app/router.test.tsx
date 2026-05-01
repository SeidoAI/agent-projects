import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, Navigate, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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

function Stub({ name }: { name: string }) {
  return <div>{name}</div>;
}

function renderRoute(path: string) {
  const routes = [
    {
      path: "/p/:projectId",
      element: <ProjectShell />,
      children: [
        { index: true, element: <Navigate to="board" replace /> },
        { path: "board", element: <Stub name="Board" /> },
        { path: "graph", element: <Stub name="ConceptGraph" /> },
        { path: "sessions", element: <Stub name="SessionList" /> },
        { path: "workflow", element: <Stub name="WorkflowMap" /> },
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
  it("renders ProjectShell with breadcrumb project id at /p/:projectId/board", () => {
    renderRoute("/p/proj-1/board");
    // ScreenShell breadcrumb + project chip both render the project id
    // ("Workspace / proj-1" + the chip in the side rail).
    expect(screen.getAllByText("proj-1").length).toBeGreaterThan(0);
    // Board stub renders inside the outlet
    expect(screen.getByText("Board")).toBeDefined();
  });

  it("renders the cream-palette nav items in the side rail", () => {
    renderRoute("/p/proj-1/board");
    // Lowercase nav per spec §3.1 C0.3.
    expect(screen.getByRole("link", { name: /overview/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /board/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /workflow/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /concepts/ })).toBeDefined();
    expect(screen.getByRole("link", { name: /sessions/ })).toBeDefined();
  });

  it("renders the workflow stub at /workflow", () => {
    renderRoute("/p/proj-1/workflow");
    expect(screen.getByText("WorkflowMap")).toBeDefined();
  });
});
