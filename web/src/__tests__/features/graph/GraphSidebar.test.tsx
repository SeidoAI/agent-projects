import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CATEGORY_COLLAPSE_THRESHOLD, GraphSidebar } from "@/features/graph/GraphSidebar";
import type { ReactFlowGraph, ReactFlowNode } from "@/lib/api/endpoints/graph";

function graph(): ReactFlowGraph {
  return {
    nodes: [
      {
        id: "user-model",
        type: "concept",
        position: { x: 0, y: 0 },
        data: { label: "User model", type: "model" },
      },
      {
        id: "auth-flow",
        type: "concept",
        position: { x: 0, y: 0 },
        data: { label: "Auth flow", type: "decision" },
      },
      {
        id: "session-svc",
        type: "concept",
        position: { x: 0, y: 0 },
        data: { label: "Session service", type: "service" },
      },
      {
        id: "KUI-1",
        type: "issue",
        position: { x: 0, y: 0 },
        data: { label: "Login endpoint" },
      },
    ],
    edges: [],
    meta: {
      kind: "concept",
      focus: null,
      upstream: false,
      downstream: false,
      depth: null,
      node_count: 4,
      edge_count: 0,
      orphans: [],
    },
  };
}

describe("GraphSidebar", () => {
  afterEach(() => cleanup());

  it("groups concept nodes by their type and lists each name", () => {
    render(<GraphSidebar graph={graph()} selectedId={null} onSelect={() => {}} />);
    // Group headers (Geist Mono uppercase by spec).
    expect(screen.getByText(/^model$/i)).toBeInTheDocument();
    expect(screen.getByText(/^decision$/i)).toBeInTheDocument();
    expect(screen.getByText(/^service$/i)).toBeInTheDocument();
    // Concept names render under their group.
    expect(screen.getByRole("button", { name: /User model/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Auth flow/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Session service/ })).toBeInTheDocument();
  });

  it("excludes issue-typed nodes (kind=issue) from the outline tree", () => {
    render(<GraphSidebar graph={graph()} selectedId={null} onSelect={() => {}} />);
    expect(screen.queryByRole("button", { name: /Login endpoint/ })).toBeNull();
  });

  it("highlights the currently-selected concept", () => {
    render(<GraphSidebar graph={graph()} selectedId="auth-flow" onSelect={() => {}} />);
    const btn = screen.getByRole("button", { name: /Auth flow/ });
    expect(btn).toHaveAttribute("aria-current", "true");
  });

  it("invokes onSelect when a concept row is clicked", () => {
    const onSelect = vi.fn();
    render(<GraphSidebar graph={graph()} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /User model/ }));
    expect(onSelect).toHaveBeenCalledWith("user-model");
  });

  describe("collapsible categories (PM #25 round 2 P2)", () => {
    it("renders a per-category count chip", () => {
      render(<GraphSidebar graph={graph()} selectedId={null} onSelect={() => {}} />);
      // Three single-member categories in this fixture.
      expect(screen.getByTestId("graph-sidebar-count-model")).toHaveTextContent("1");
      expect(screen.getByTestId("graph-sidebar-count-decision")).toHaveTextContent("1");
      expect(screen.getByTestId("graph-sidebar-count-service")).toHaveTextContent("1");
    });

    it("renders a color square per category derived from KIND_COLOR", () => {
      const { container } = render(
        <GraphSidebar graph={graph()} selectedId={null} onSelect={() => {}} />,
      );
      // model → --color-ink, decision → --color-tripwire, service →
      // --color-info per the kind→token map.
      const modelSquare = container.querySelector(
        "[data-testid='graph-sidebar-color-model']",
      ) as HTMLElement | null;
      const decisionSquare = container.querySelector(
        "[data-testid='graph-sidebar-color-decision']",
      ) as HTMLElement | null;
      const serviceSquare = container.querySelector(
        "[data-testid='graph-sidebar-color-service']",
      ) as HTMLElement | null;
      expect(modelSquare?.style.backgroundColor).toBe("var(--color-ink)");
      expect(decisionSquare?.style.backgroundColor).toBe("var(--color-tripwire)");
      expect(serviceSquare?.style.backgroundColor).toBe("var(--color-info)");
    });

    it("toggles aria-expanded on the category caret button", () => {
      render(<GraphSidebar graph={graph()} selectedId={null} onSelect={() => {}} />);
      // Few categories → defaults to expanded.
      const modelHeader = screen.getByText(/^model$/i).closest("button");
      expect(modelHeader).not.toBeNull();
      expect(modelHeader).toHaveAttribute("aria-expanded", "true");
      // Concept row visible when expanded.
      expect(screen.getByRole("button", { name: /User model/ })).toBeInTheDocument();
      // Click collapses.
      fireEvent.click(modelHeader as HTMLElement);
      expect(modelHeader).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("button", { name: /User model/ })).toBeNull();
    });

    it(
      `defaults categories collapsed when there are more than ` +
        `CATEGORY_COLLAPSE_THRESHOLD distinct kinds, except the one ` +
        `holding the selected node`,
      () => {
        // Build a graph with more than the threshold's worth of
        // distinct kinds. Selected node lives in "model".
        const kinds = [
          "model",
          "decision",
          "service",
          "schema",
          "endpoint",
          "contract",
          "requirement",
          "custom",
        ];
        expect(kinds.length).toBeGreaterThan(CATEGORY_COLLAPSE_THRESHOLD);
        const nodes: ReactFlowNode[] = kinds.map((k) => ({
          id: `${k}-node`,
          type: "concept",
          position: { x: 0, y: 0 },
          data: { label: `${k} node`, type: k },
        }));
        const big: ReactFlowGraph = {
          nodes,
          edges: [],
          meta: {
            kind: "concept",
            focus: null,
            upstream: false,
            downstream: false,
            depth: null,
            node_count: nodes.length,
            edge_count: 0,
            orphans: [],
          },
        };
        render(<GraphSidebar graph={big} selectedId="model-node" onSelect={() => {}} />);
        // Selected category expanded.
        const modelHeader = screen.getByText(/^model$/i).closest("button");
        expect(modelHeader).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("button", { name: /^model node$/i })).toBeInTheDocument();
        // A non-selected category is collapsed.
        const schemaHeader = screen.getByText(/^schema$/i).closest("button");
        expect(schemaHeader).toHaveAttribute("aria-expanded", "false");
        expect(screen.queryByRole("button", { name: /^schema node$/i })).toBeNull();
      },
    );
  });
});
