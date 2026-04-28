import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GraphLegend } from "@/features/graph/GraphLegend";

describe("GraphLegend", () => {
  afterEach(() => cleanup());

  it("renders the four canonical legend rows from the design mockup", () => {
    render(<GraphLegend />);
    expect(screen.getByText(/fresh concept/i)).toBeInTheDocument();
    expect(screen.getByText(/stale concept/i)).toBeInTheDocument();
    expect(screen.getByText(/^cites$/i)).toBeInTheDocument();
    expect(screen.getByText(/^related$/i)).toBeInTheDocument();
  });
});
