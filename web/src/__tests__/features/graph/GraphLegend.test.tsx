import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GraphLegend } from "@/features/graph/GraphLegend";

describe("GraphLegend", () => {
  afterEach(() => cleanup());

  it("renders the canonical legend rows from the design mockup", () => {
    render(<GraphLegend />);
    // Post-#76 the legend collapsed "fresh concept / stale concept"
    // labels into per-type-group rows + a single `stale` chip; the
    // three relationship-kind labels (`stale`, `cites`, `related`)
    // are the stable contract.
    expect(screen.getByText(/^stale$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cites$/i)).toBeInTheDocument();
    expect(screen.getByText(/^related$/i)).toBeInTheDocument();
  });
});
