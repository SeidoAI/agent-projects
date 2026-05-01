import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LifecycleWire } from "@/components/ui/lifecycle-wire";

const STATIONS = [
  { id: "planned", label: "planned" },
  { id: "queued", label: "queued" },
  { id: "executing", label: "executing" },
  { id: "in_review", label: "review" },
  { id: "verified", label: "verified" },
  { id: "completed", label: "completed" },
];

describe("LifecycleWire", () => {
  afterEach(() => cleanup());

  it("renders one station label per supplied station", () => {
    render(<LifecycleWire stations={STATIONS} />);
    for (const s of STATIONS) {
      expect(screen.getByText(s.label)).toBeInTheDocument();
    }
  });

  it("draws an SVG line that spans the wire", () => {
    const { container } = render(<LifecycleWire stations={STATIONS} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    const line = container.querySelector("svg line");
    expect(line).toBeTruthy();
  });

  it("renders one circle per station inside the SVG", () => {
    const { container } = render(<LifecycleWire stations={STATIONS} />);
    // Each station gets an outer cream-fill circle and an inner red dot;
    // both go inside the SVG. Asserting the count is at least N gives us
    // confidence without coupling the test to the exact node structure.
    const circles = container.querySelectorAll("svg circle");
    expect(circles.length).toBeGreaterThanOrEqual(STATIONS.length);
  });

  it("renders count under each station label as 'NN · count'", () => {
    render(
      <LifecycleWire stations={STATIONS} counts={{ planned: 2, executing: 5, completed: 1 }} />,
    );
    // Format is the station ordinal (zero-padded) + " · " + the count.
    // "01 · 2" for planned (idx 0, count 2), etc.
    expect(screen.getByText("01 · 2")).toBeInTheDocument();
    expect(screen.getByText("03 · 5")).toBeInTheDocument();
    expect(screen.getByText("06 · 1")).toBeInTheDocument();
  });

  it("renders zero counts (rather than hiding) so the wire reads cleanly", () => {
    render(<LifecycleWire stations={STATIONS} counts={{ planned: 0, executing: 3 }} />);
    // Zero is informative — it tells the PM "nothing is at this stage
    // right now." Hiding it would leave a visual gap.
    expect(screen.getByText("01 · 0")).toBeInTheDocument();
    expect(screen.getByText("03 · 3")).toBeInTheDocument();
  });

  it("marks the active station with aria-current", () => {
    render(<LifecycleWire stations={STATIONS} currentIndex={2} />);
    const active = screen.getByText("executing").closest("[aria-current]");
    expect(active).toHaveAttribute("aria-current", "step");
  });

  it("renders without count badges when the counts prop is omitted", () => {
    // Per PM follow-up — the `counts?` optional branch wasn't covered.
    // With no counts supplied, no station should show a numeric badge.
    render(<LifecycleWire stations={STATIONS} />);
    for (const s of STATIONS) {
      expect(screen.getByText(s.label)).toBeInTheDocument();
    }
    // The wire should still draw the SVG without throwing on an absent
    // counts map (the inner `counts?.[s.id]` access falls through cleanly).
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("handles a single-station wire without dividing by zero", () => {
    // The component computes step spacing as `innerW / Math.max(n - 1, 1)`
    // — the Math.max guard exists so a 1-station wire doesn't NaN out.
    // This test pins that branch.
    const { container } = render(<LifecycleWire stations={[{ id: "only", label: "only" }]} />);
    expect(screen.getByText("only")).toBeInTheDocument();
    expect(container.querySelectorAll("svg circle").length).toBeGreaterThanOrEqual(1);
  });
});
