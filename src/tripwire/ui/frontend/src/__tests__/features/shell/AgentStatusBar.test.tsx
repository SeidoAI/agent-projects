import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { AgentStatusBar } from "@/features/shell/AgentStatusBar";

describe("AgentStatusBar", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the placeholder icon + '0 agents running' text", () => {
    render(
      <TooltipProvider>
        <AgentStatusBar />
      </TooltipProvider>,
    );
    expect(screen.getByText("0 agents running")).toBeInTheDocument();
  });

  it("exposes the v2 message via aria-label and native title", () => {
    render(
      <TooltipProvider>
        <AgentStatusBar />
      </TooltipProvider>,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveAccessibleName(
      "Agent monitoring ships in v2 — requires tripwire.containers",
    );
    expect(status).toHaveAttribute(
      "title",
      "Agent monitoring ships in v2 — requires tripwire.containers",
    );
  });

  it("does not make any network calls", () => {
    render(
      <TooltipProvider>
        <AgentStatusBar />
      </TooltipProvider>,
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
