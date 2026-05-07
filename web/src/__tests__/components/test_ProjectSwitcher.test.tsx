import { fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { useLocation } from "react-router-dom";
import { describe, expect, test } from "vitest";

import {
  ProjectSwitcher,
  phaseTone,
  sortProjects,
  swapProjectIdInPath,
} from "@/components/ProjectSwitcher";
import type { ProjectSummary } from "@/lib/api/endpoints/project";

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

describe("sortProjects", () => {
  test("sorts by friendly name (project- prefix stripped)", () => {
    const result = sortProjects([
      projectSummary({ id: "1", name: "project-zebra" }),
      projectSummary({ id: "2", name: "project-aardvark" }),
      projectSummary({ id: "3", name: "middle" }),
    ]);
    expect(result.map((p) => p.name)).toEqual([
      "project-aardvark",
      "middle",
      "project-zebra",
    ]);
  });

  test("returns a new array (does not mutate input)", () => {
    const input = [
      projectSummary({ id: "1", name: "b" }),
      projectSummary({ id: "2", name: "a" }),
    ];
    const result = sortProjects(input);
    expect(input.map((p) => p.id)).toEqual(["1", "2"]);
    expect(result.map((p) => p.id)).toEqual(["2", "1"]);
  });
});

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

describe("<ProjectSwitcher />", () => {
  test("renders projects in a flat alphabetical list", async () => {
    server.use(
      http.get("/api/projects", () =>
        HttpResponse.json([
          projectSummary({ id: "p1", name: "zebra" }),
          projectSummary({ id: "p2", name: "alpha" }),
          projectSummary({ id: "p3", name: "middle" }),
        ]),
      ),
    );

    renderWithProviders(
      <ProjectSwitcher projectId="p2" currentLabel="alpha" />,
      { initialPath: "/p/p2/board" },
    );

    openDropdown(screen.getByRole("button", { name: /switch project/i }));
    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /alpha/ })).toBeInTheDocument();
    });
    // No workspace headings — flat list only.
    expect(screen.queryByText(/Unworkspaced/i)).not.toBeInTheDocument();
    // Order: alpha, middle, zebra (alphabetical, project- prefix stripped).
    const items = screen.getAllByRole("menuitem").map((el) => el.textContent);
    const projectItems = items.filter((t) =>
      /alpha|middle|zebra/.test(t ?? ""),
    );
    expect(projectItems[0]).toMatch(/alpha/);
    expect(projectItems[1]).toMatch(/middle/);
    expect(projectItems[2]).toMatch(/zebra/);
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

  test("renders project phase as the dropdown badge", async () => {
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
