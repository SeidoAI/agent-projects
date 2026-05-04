import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IssuesGraphView } from "@/features/board/IssuesGraphView";
import type { EnumValue } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";

afterEach(() => cleanup());

function makeIssue(overrides: Partial<IssueSummary>): IssueSummary {
  return {
    id: "K-1",
    title: "issue",
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

const STATUS_VALUES: EnumValue[] = [
  { value: "backlog", label: "Backlog", color: "#888888", description: null },
  { value: "in_progress", label: "In progress", color: "#3366cc", description: null },
  { value: "done", label: "Done", color: "#33aa33", description: null },
];

describe("IssuesGraphView", () => {
  it("renders an empty state when no issues are passed", () => {
    render(<IssuesGraphView issues={[]} statusValues={STATUS_VALUES} onNodeClick={() => {}} />);
    expect(screen.getByTestId("issues-graph-empty")).toBeInTheDocument();
  });

  it("renders a node per issue with the issue id and truncated title", () => {
    const issues = [
      makeIssue({ id: "K-1", title: "Implement auth", status: "in_progress" }),
      makeIssue({ id: "K-2", title: "Add migrations", status: "backlog" }),
    ];
    render(
      <IssuesGraphView issues={issues} statusValues={STATUS_VALUES} onNodeClick={() => {}} />,
    );
    expect(screen.getByTestId("issues-graph-node-K-1")).toBeInTheDocument();
    expect(screen.getByTestId("issues-graph-node-K-2")).toBeInTheDocument();
    expect(screen.getByText("K-1")).toBeInTheDocument();
    expect(screen.getByText("Implement auth")).toBeInTheDocument();
  });

  it("emits a path per blocked_by edge that resolves to a visible issue", () => {
    const issues = [
      makeIssue({ id: "K-1", title: "Root" }),
      makeIssue({ id: "K-2", title: "Mid", blocked_by: ["K-1"] }),
      makeIssue({ id: "K-3", title: "Leaf", blocked_by: ["K-2"] }),
    ];
    const { container } = render(
      <IssuesGraphView issues={issues} statusValues={STATUS_VALUES} onNodeClick={() => {}} />,
    );
    const paths = container.querySelectorAll("g[data-layer=edges] path");
    expect(paths).toHaveLength(2);
  });

  it("ignores blocked_by ids that do not resolve to a visible issue", () => {
    const issues = [
      makeIssue({ id: "K-1", title: "Lonely", blocked_by: ["K-99"] }),
    ];
    const { container } = render(
      <IssuesGraphView issues={issues} statusValues={STATUS_VALUES} onNodeClick={() => {}} />,
    );
    const paths = container.querySelectorAll("g[data-layer=edges] path");
    expect(paths).toHaveLength(0);
  });

  it("invokes onNodeClick with the full issue when a node is clicked", () => {
    const onNodeClick = vi.fn();
    const issues = [makeIssue({ id: "K-7", title: "Click target" })];
    render(
      <IssuesGraphView
        issues={issues}
        statusValues={STATUS_VALUES}
        onNodeClick={onNodeClick}
      />,
    );
    fireEvent.click(screen.getByTestId("issues-graph-node-K-7"));
    expect(onNodeClick).toHaveBeenCalledTimes(1);
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ id: "K-7" }));
  });

  it("focuses a node on click — focus state visibly flips on the node", () => {
    const issues = [makeIssue({ id: "K-5", title: "Focusable" })];
    render(
      <IssuesGraphView issues={issues} statusValues={STATUS_VALUES} onNodeClick={() => {}} />,
    );
    const node = screen.getByTestId("issues-graph-node-K-5");
    expect(node).toHaveAttribute("data-focus", "false");
    fireEvent.click(node);
    expect(node).toHaveAttribute("data-focus", "true");
  });

  it("supports keyboard activation (Enter / Space)", () => {
    const onNodeClick = vi.fn();
    const issues = [makeIssue({ id: "K-9", title: "Keyboard" })];
    render(
      <IssuesGraphView
        issues={issues}
        statusValues={STATUS_VALUES}
        onNodeClick={onNodeClick}
      />,
    );
    const node = screen.getByTestId("issues-graph-node-K-9");
    fireEvent.keyDown(node, { key: "Enter" });
    expect(onNodeClick).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(node, { key: " " });
    expect(onNodeClick).toHaveBeenCalledTimes(2);
  });

  it("uses status enum colour for the node fill (transitive — surfaced via stroke attr)", () => {
    const issues = [makeIssue({ id: "K-1", title: "Colored", status: "in_progress" })];
    const { container } = render(
      <IssuesGraphView issues={issues} statusValues={STATUS_VALUES} onNodeClick={() => {}} />,
    );
    const rect = container.querySelector('g[data-testid="issues-graph-node-K-1"] rect');
    expect(rect).not.toBeNull();
    expect(rect?.getAttribute("stroke")).toBe("#3366cc");
  });
});
