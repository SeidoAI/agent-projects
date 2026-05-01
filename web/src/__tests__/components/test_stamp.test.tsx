import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Stamp } from "@/components/ui/stamp";

describe("Stamp", () => {
  afterEach(() => cleanup());

  it("renders children inside a span with the mono font + uppercase styling", () => {
    render(<Stamp>KUI-101</Stamp>);
    const stamp = screen.getByText("KUI-101");
    expect(stamp.tagName).toBe("SPAN");
    expect(stamp).toHaveClass("uppercase");
    expect(stamp).toHaveClass("font-mono");
  });

  it("uses the default tone (ink border) when no tone is supplied", () => {
    render(<Stamp data-testid="s">DEFAULT</Stamp>);
    const stamp = screen.getByTestId("s");
    expect(stamp).toHaveAttribute("data-tone", "default");
  });

  it("applies the gate tone for validators", () => {
    render(
      <Stamp tone="gate" data-testid="s">
        VALIDATOR
      </Stamp>,
    );
    expect(screen.getByTestId("s")).toHaveAttribute("data-tone", "gate");
  });

  it("applies the rule tone for tripwire surfaces", () => {
    render(
      <Stamp tone="rule" data-testid="s">
        TRIPWIRE
      </Stamp>,
    );
    expect(screen.getByTestId("s")).toHaveAttribute("data-tone", "rule");
  });

  it("identifier variant uses the identifier semantics", () => {
    render(
      <Stamp variant="identifier" data-testid="s">
        S001
      </Stamp>,
    );
    expect(screen.getByTestId("s")).toHaveAttribute("data-variant", "identifier");
  });

  it("merges custom className with built-in classes", () => {
    render(
      <Stamp className="extra-class" data-testid="s">
        X
      </Stamp>,
    );
    const stamp = screen.getByTestId("s");
    expect(stamp).toHaveClass("extra-class");
    expect(stamp).toHaveClass("uppercase");
  });
});
