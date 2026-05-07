import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { useLocation } from "react-router-dom";
import { describe, expect, test } from "vitest";

import {
  ProjectSwitcher,
  groupProjectsByWorkspace,
  phaseTone,
  swapProjectIdInPath,
} from "@/components/ProjectSwitcher";
import type { ProjectSummary } from "@/lib/api/endpoints/project";
import type { WorkspaceSummary } from "@/lib/api/endpoints/workspace";

import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";

function openDropdown(trigger: HTMLElement) {
  // Radix DropdownMenu opens on pointerdown + pointerup, not click;
  // jsdom doesn't fire pointer events for fireEvent.click. Mirror the
  // pattern from test_IssueDetail.test.tsx::openDropdown.
  fireEvent.pointerDown(trigger, { button: 0, pointerType: "mouse" });
  fireEvent.pointerUp(trigger, { button: 0, pointerType: "mouse" });
}

function projectSummary(p: Partial<ProjectSummary>): ProjectSummary {
  return {
    id: p.id ?? "x",
    name: p.name ?? "x",
    key_prefix: p.key_prefix ?? "X",
    phase: "scoping",
    issue_count: 0,
    node_count: 0,
    session_count: 0,
    workspace_id: null,
    ...p,
  };
}

function workspaceSummary(w: Partial<WorkspaceSummary>): WorkspaceSummary {
  return {
    id: w.id ?? "ws-1",
    name: w.name ?? "Workspace",
    slug: w.slug ?? "ws",
    dir: w.dir ?? "/tmp",
    description: "",
    project_slugs: [],
    ...w,
  };
}

describe("phaseTone", () => {
  test("maps each canonical phase to a distinct tone", () => {
    expect(phaseTone("scoping")).toBe("info");
    expect(phaseTone("scoped")).toBe("default");
    expect(phaseTone("executing")).toBe("rule");
    expect(phaseTone("reviewing")).toBe("gate");
  });

  test("falls back to default for unknown phases", () => {
    expect(phaseTone("unknown")).toBe("default");
    expect(phaseTone("")).toBe("default");
  });
});

describe("groupProjectsByWorkspace", () => {
  test("flat list when no workspaces are configured", () => {
    const projects = [
      projectSummary({ id: "a", name: "alpha" }),
      projectSummary({ id: "b", name: "beta" }),
    ];
    const groups = groupProjectsByWorkspace(projects, []);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.workspaceId).toBe("__none__");
    expect(groups[0]?.projects.map((p) => p.id)).toEqual(["a", "b"]);
  });

  test("groups by workspace_id and orders workspaces by name", () => {
    const wsA = workspaceSummary({ id: "wsa", name: "Alpha workspace" });
    const wsB = workspaceSummary({ id: "wsb", name: "Bravo workspace" });
    const projects = [
      projectSummary({ id: "1", name: "in-bravo", workspace_id: "wsb" }),
      projectSummary({ id: "2", name: "in-alpha", workspace_id: "wsa" }),
      projectSummary({ id: "3", name: "no-ws" }),
    ];
    const groups = groupProjectsByWorkspace(projects, [wsA, wsB]);
    expect(groups.map((g) => g.workspaceName)).toEqual([
      "Alpha workspace",
      "Bravo workspace",
      "Unworkspaced",
    ]);
  });

  test("Unworkspaced group is always last", () => {
    const ws = workspaceSummary({ id: "z", name: "Zulu" });
    const groups = groupProjectsByWorkspace(
      [
        projectSummary({ id: "u", name: "u" }),
        projectSummary({ id: "z", name: "z", workspace_id: "z" }),
      ],
      [ws],
    );
    const last = groups[groups.length - 1];
    expect(last?.workspaceName).toBe("Unworkspaced");
  });

  test("projects within a group are sorted by friendly name", () => {
    const ws = workspaceSummary({ id: "ws", name: "WS" });
    const projects = [
      projectSummary({ id: "1", name: "project-zebra", workspace_id: "ws" }),
      projectSummary({ id: "2", name: "project-aardvark", workspace_id: "ws" }),
    ];
    const groups = groupProjectsByWorkspace(projects, [ws]);
    expect(groups[0]?.projects.map((p) => p.name)).toEqual([
      "project-aardvark",
      "project-zebra",
    ]);
  });

  test("project with workspace_id not in discovered list collapses into Unworkspaced", () => {
    // Realistic cause: cache race where /api/projects ships ahead of
    // /api/workspaces, or a stale workspace_id from before the user
    // removed a workspace_root from config. Either way, surfacing an
    // "Unknown workspace" group has no useful UI affordance — the
    // project lands in Unworkspaced, which is recoverable.
    const projects = [
      projectSummary({ id: "x", name: "x", workspace_id: "ghost-ws" }),
    ];
    const groups = groupProjectsByWorkspace(projects, []);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.workspaceId).toBe("__none__");
    expect(groups[0]?.workspaceName).toBe("Unworkspaced");
    expect(groups[0]?.projects.map((p) => p.id)).toEqual(["x"]);
  });
});

describe("swapProjectIdInPath", () => {
  test("preserves sub-path", () => {
    expect(swapProjectIdInPath("/p/A/board", "A", "B")).toBe("/p/B/board");
  });

  test("preserves deep nested path", () => {
    expect(swapProjectIdInPath("/p/A/issues/KUI-1", "A", "B")).toBe(
      "/p/B/issues/KUI-1",
    );
  });

  test("handles bare project root", () => {
    expect(swapProjectIdInPath("/p/A", "A", "B")).toBe("/p/B");
  });

  test("falls back to bare /p/{newId} when path doesn't match", () => {
    expect(swapProjectIdInPath("/something-else", "A", "B")).toBe("/p/B");
  });

  test("doesn't replace substrings of other ids", () => {
    // `/p/AB/x` shouldn't be touched by an A→C swap.
    expect(swapProjectIdInPath("/p/AB/x", "A", "C")).toBe("/p/C");
  });
});

describe("<ProjectSwitcher />", () => {
  test("renders flat list when no workspaces are configured", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([
          projectSummary({ id: "p1", name: "alpha", key_prefix: "ALP" }),
          projectSummary({ id: "p2", name: "beta", key_prefix: "BET" }),
        ]),
      ),
    );

    renderWithProviders(
      <ProjectSwitcher projectId="p1" currentLabel="alpha" />,
      { initialPath: "/p/p1/board" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("menuitem", { name: /alpha/ }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("menuitem", { name: /beta/ })).toBeInTheDocument();
    // No workspace heading rendered when there's only one (Unworkspaced) group.
    expect(screen.queryByText(/Unworkspaced/i)).not.toBeInTheDocument();
  });

  test("groups projects under workspace headings", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([
          projectSummary({
            id: "p1",
            name: "kb-pivot",
            key_prefix: "KBP",
            workspace_id: "ws-seido",
          }),
          projectSummary({
            id: "p2",
            name: "graph-ui-v2",
            key_prefix: "GUI",
            workspace_id: "ws-seido",
          }),
          projectSummary({ id: "p3", name: "loose", key_prefix: "LSE" }),
        ]),
      ),
      http.get("/api/workspaces", () =>
        HttpResponse.json([
          workspaceSummary({ id: "ws-seido", name: "Seido", slug: "seido" }),
        ]),
      ),
    );

    renderWithProviders(
      <ProjectSwitcher projectId="p1" currentLabel="kb-pivot" />,
      { initialPath: "/p/p1" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() => {
      expect(screen.getByText("Seido")).toBeInTheDocument();
    });
    expect(screen.getByText("Unworkspaced")).toBeInTheDocument();
    // Scope to menu items so we don't double-match the trigger label.
    expect(
      screen.getByRole("menuitem", { name: /kb-pivot/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /graph-ui-v2/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: /loose/ }),
    ).toBeInTheDocument();
  });

  test("clicking a project navigates while preserving sub-path", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([
          projectSummary({ id: "p1", name: "alpha" }),
          projectSummary({ id: "p2", name: "beta" }),
        ]),
      ),
    );

    let observedPath = "";
    function PathProbe() {
      const loc = useLocation();
      observedPath = loc.pathname;
      return null;
    }

    renderWithProviders(
      <>
        <ProjectSwitcher projectId="p1" currentLabel="alpha" />
        <PathProbe />
      </>,
      { initialPath: "/p/p1/board" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /beta/ })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: /beta/ }));

    await waitFor(() => expect(observedPath).toBe("/p/p2/board"));
  });

  test("renders project phase as the dropdown badge (replaces issue key)", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([
          projectSummary({
            id: "p1",
            name: "alpha",
            key_prefix: "ALP",
            phase: "executing",
          }),
        ]),
      ),
    );

    renderWithProviders(
      <ProjectSwitcher projectId="p1" currentLabel="alpha" />,
      { initialPath: "/p/p1/board" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    const item = await screen.findByRole("menuitem", { name: /alpha/ });
    // The phase appears as the right-side badge.
    expect(item.textContent).toContain("executing");
    // The pre-v0.11 issue-key badge is gone.
    expect(item.textContent).not.toContain("ALP");
  });

  test("renders fallback when projects list is empty", async () => {
    server.use(http.get("/api/projects", () => HttpResponse.json([])));

    renderWithProviders(
      <ProjectSwitcher projectId="p1" currentLabel="(loading)" />,
      { initialPath: "/p/p1" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() => {
      expect(screen.getByText(/no projects discovered/i)).toBeInTheDocument();
    });
  });

  test("Open another project link navigates to picker", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([projectSummary({ id: "p1", name: "alpha" })]),
      ),
    );

    let observedPath = "";
    function PathProbe() {
      const loc = useLocation();
      observedPath = loc.pathname;
      return null;
    }

    renderWithProviders(
      <>
        <ProjectSwitcher projectId="p1" currentLabel="alpha" />
        <PathProbe />
      </>,
      { initialPath: "/p/p1/board" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() => {
      expect(screen.getByText(/open another project/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/open another project/i));
    await waitFor(() => expect(observedPath).toBe("/"));
  });
});
