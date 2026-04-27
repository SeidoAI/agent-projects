import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FilterPills } from "@/features/board/FilterPills";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

const baseProps = {
  agents: ["alice", "bob"],
  owners: ["maintainer", "@me"],
  ages: ["today", "this-week", "this-month", "older"],
  selectedAgents: new Set<string>(),
  selectedOwners: new Set<string>(),
  selectedAges: new Set<string>(),
  hasBlockedInbox: false,
  blocked: false,
  onToggleAgent: () => {},
  onToggleOwner: () => {},
  onToggleAge: () => {},
  onToggleBlockedInbox: () => {},
  onToggleBlocked: () => {},
  onClearAll: () => {},
};

describe("FilterPills", () => {
  it("renders all filter dimensions", () => {
    renderWithProviders(<FilterPills {...baseProps} />);
    expect(screen.getByRole("button", { name: /^alice$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^bob$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^maintainer$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^this-week$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open blocked inbox entry/i })).toBeInTheDocument();
  });

  it("never renders a `has-tripwires` pill — replaced by has-blocked-inbox-entry", () => {
    renderWithProviders(<FilterPills {...baseProps} />);
    // Tripwires are agent-facing per dec-tripwires-are-agent-facing —
    // surfacing them as a human filter would be a category mistake.
    expect(screen.queryByRole("button", { name: /tripwire/i })).not.toBeInTheDocument();
  });

  it("calls the right toggle handler when a pill is clicked", () => {
    const onToggleAgent = vi.fn();
    const onToggleBlockedInbox = vi.fn();
    renderWithProviders(
      <FilterPills
        {...baseProps}
        onToggleAgent={onToggleAgent}
        onToggleBlockedInbox={onToggleBlockedInbox}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^alice$/i }));
    expect(onToggleAgent).toHaveBeenCalledWith("alice");
    fireEvent.click(screen.getByRole("button", { name: /open blocked inbox entry/i }));
    expect(onToggleBlockedInbox).toHaveBeenCalled();
  });

  it("renders selected pills with aria-pressed=true", () => {
    renderWithProviders(
      <FilterPills {...baseProps} selectedAgents={new Set(["alice"])} hasBlockedInbox={true} />,
    );
    expect(screen.getByRole("button", { name: /^alice$/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /^bob$/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /open blocked inbox entry/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows a clear-all chip when at least one filter is active", () => {
    const onClearAll = vi.fn();
    const { rerender } = renderWithProviders(<FilterPills {...baseProps} />);
    expect(screen.queryByRole("button", { name: /clear filters/i })).not.toBeInTheDocument();
    rerender(
      <FilterPills {...baseProps} selectedAgents={new Set(["alice"])} onClearAll={onClearAll} />,
    );
    const clear = screen.getByRole("button", { name: /clear filters/i });
    fireEvent.click(clear);
    expect(onClearAll).toHaveBeenCalled();
  });
});
