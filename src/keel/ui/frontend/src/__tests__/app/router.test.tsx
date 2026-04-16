import { Placeholder } from "@/app/Placeholder";
import { ProjectShell } from "@/app/ProjectShell";
import { V2Placeholder } from "@/app/V2Placeholder";
import { cleanup, render, screen } from "@testing-library/react";
import { Navigate, RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

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
        { path: "orchestration", element: <Placeholder name="OrchestrationView" /> },
        { path: "messages", element: <V2Placeholder feature="Messages" /> },
        { path: "agents", element: <V2Placeholder feature="Agents" /> },
      ],
    },
  ];
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe("Router", () => {
  it("renders ProjectList placeholder at /projects", () => {
    renderRoute("/projects");
    expect(screen.getByText("ProjectList")).toBeDefined();
    expect(screen.getByText("Coming in a later issue.")).toBeDefined();
  });

  it("renders ProjectShell with TopBar at /p/:projectId/board", () => {
    renderRoute("/p/proj-1/board");
    // TopBar renders the project name
    expect(screen.getByText("Project proj-1")).toBeDefined();
    // Board placeholder renders inside the outlet
    expect(screen.getByText("KanbanBoard")).toBeDefined();
  });

  it("renders V2Placeholder for /p/:projectId/messages", () => {
    renderRoute("/p/proj-1/messages");
    expect(screen.getByRole("heading", { name: "Messages" })).toBeDefined();
    expect(screen.getByText(/Coming in v2/)).toBeDefined();
  });

  it("renders V2Placeholder for /p/:projectId/agents", () => {
    renderRoute("/p/proj-1/agents");
    expect(screen.getByRole("heading", { name: "Agents" })).toBeDefined();
  });

  it("renders AgentStatusBar in shell", () => {
    renderRoute("/p/proj-1/board");
    expect(screen.getByText("0 agents running")).toBeDefined();
    expect(screen.getByText("file watcher: connected")).toBeDefined();
  });

  it("renders nav tabs in TopBar", () => {
    renderRoute("/p/proj-1/board");
    expect(screen.getByText("Board")).toBeDefined();
    expect(screen.getByText("Graph")).toBeDefined();
    expect(screen.getByText("Sessions")).toBeDefined();
    expect(screen.getByText("Orchestration")).toBeDefined();
  });
});
