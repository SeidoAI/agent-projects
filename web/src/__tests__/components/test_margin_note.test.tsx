import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MarginNote } from "@/components/ui/margin-note";

describe("MarginNote", () => {
  afterEach(() => cleanup());

  it("renders children inside an italic serif span", () => {
    render(<MarginNote>added under duress</MarginNote>);
    const note = screen.getByText("added under duress");
    expect(note).toHaveClass("italic");
    expect(note).toHaveClass("font-serif");
  });
});
