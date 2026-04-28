import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TurnStream, type TurnStreamEntry } from "@/features/live/TurnStream";

afterEach(() => cleanup());

function engagement(id: string, startedAt: string, trigger: string): TurnStreamEntry {
  return {
    kind: "engagement",
    id,
    timestamp: startedAt,
    trigger,
    endedAt: null,
    outcome: null,
  };
}

function tripwire(id: string, firedAt: string, name: string): TurnStreamEntry {
  return {
    kind: "tripwire_fire",
    id,
    timestamp: firedAt,
    tripwireId: name,
  };
}

describe("TurnStream — KUI-107 turn stream", () => {
  it("renders engagement entries oldest-to-newest with engagement-boundary dividers between consecutive engagements", () => {
    const entries: TurnStreamEntry[] = [
      engagement("eng-1", "2026-04-27T10:00:00Z", "spawn"),
      tripwire("tw-1", "2026-04-27T11:00:00Z", "no-merge-without-self-review"),
      engagement("eng-2", "2026-04-27T14:10:00Z", "resume"),
    ];

    render(<TurnStream entries={entries} />);

    // Both engagements rendered.
    const engagementMarkers = screen.getAllByTestId("engagement-marker");
    expect(engagementMarkers).toHaveLength(2);

    // Engagement #2's boundary divider names the engagement number,
    // its trigger, and its start time per the v0.8.x amendment.
    const eng2 = engagementMarkers[1];
    expect(eng2).toHaveTextContent(/engagement #2/i);
    expect(eng2).toHaveTextContent(/resume/i);

    // Tripwire-fire copy is reframed per [[dec-tripwires-are-agent-facing]] —
    // no "alert" / "warning" language, agent-facing framing instead.
    const fire = screen.getByTestId("tripwire-fire-tw-1");
    expect(fire).toHaveTextContent(/agent received tripwire/i);
    expect(fire).not.toHaveTextContent(/alert/i);
    expect(fire).not.toHaveTextContent(/warning/i);
  });

  it("shows the jump-to-live pill when the user has scrolled away from the bottom, hides it at the bottom", () => {
    const entries: TurnStreamEntry[] = [engagement("eng-1", "2026-04-27T10:00:00Z", "spawn")];
    render(<TurnStream entries={entries} />);

    const container = screen.getByTestId("turn-stream-scroll");

    // Initially at bottom (jsdom defaults: scrollHeight=0, scrollTop=0,
    // clientHeight=0). The pill is hidden.
    expect(screen.queryByRole("button", { name: /jump to live/i })).toBeNull();

    // Simulate the user scrolling up — the container reports
    // significant unviewed content below the visible window.
    Object.defineProperty(container, "scrollHeight", {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(container, "clientHeight", {
      value: 200,
      configurable: true,
    });
    Object.defineProperty(container, "scrollTop", {
      value: 100,
      configurable: true,
    });
    fireEvent.scroll(container);

    expect(screen.getByRole("button", { name: /jump to live/i })).toBeVisible();
  });

  it("re-hides the jump-to-live pill after the user scrolls back near the bottom", () => {
    render(<TurnStream entries={[engagement("eng-1", "2026-04-27T10:00:00Z", "spawn")]} />);
    const container = screen.getByTestId("turn-stream-scroll");

    // First, scroll up to surface the pill.
    Object.defineProperty(container, "scrollHeight", {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(container, "clientHeight", {
      value: 200,
      configurable: true,
    });
    Object.defineProperty(container, "scrollTop", {
      value: 100,
      configurable: true,
    });
    fireEvent.scroll(container);
    expect(screen.getByRole("button", { name: /jump to live/i })).toBeVisible();

    // Now scroll back near the bottom — pill should disappear.
    Object.defineProperty(container, "scrollTop", {
      value: 800,
      configurable: true,
    });
    fireEvent.scroll(container);
    expect(screen.queryByRole("button", { name: /jump to live/i })).toBeNull();
  });

  it("renders an empty-state message when there are no entries", () => {
    render(<TurnStream entries={[]} />);
    expect(screen.getByTestId("turn-stream-empty")).toHaveTextContent(/waiting/i);
  });
});
