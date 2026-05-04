import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ageBucket, useBoardFilters } from "@/features/board/hooks/useBoardFilters";

function makeWrapper(initialPath: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>;
  };
}

describe("useBoardFilters", () => {
  it("defaults to sessions view, board mode, with empty filters", () => {
    const { result } = renderHook(() => useBoardFilters(), { wrapper: makeWrapper("/p/x/board") });
    expect(result.current.filters.view).toBe("sessions");
    expect(result.current.filters.mode).toBe("board");
    expect(result.current.filters.agents.size).toBe(0);
    expect(result.current.filters.hasBlockedInbox).toBe(false);
  });

  it("hydrates filters from the URL on first render", () => {
    const { result } = renderHook(() => useBoardFilters(), {
      wrapper: makeWrapper("/p/x/board?view=issues&mode=graph&agent=alice,bob&inbox=1"),
    });
    expect(result.current.filters.view).toBe("issues");
    expect(result.current.filters.mode).toBe("graph");
    expect([...result.current.filters.agents].sort()).toEqual(["alice", "bob"]);
    expect(result.current.filters.hasBlockedInbox).toBe(true);
    expect(result.current.filters.blocked).toBe(false);
  });

  it("ignores unknown mode values and falls back to board", () => {
    const { result } = renderHook(() => useBoardFilters(), {
      wrapper: makeWrapper("/p/x/board?mode=spaceship"),
    });
    expect(result.current.filters.mode).toBe("board");
  });

  it("persists view + filter changes to the URL query string", () => {
    let currentLocation = "";
    function Probe() {
      const loc = useLocation();
      currentLocation = `${loc.pathname}${loc.search}`;
      return null;
    }
    const { result } = renderHook(() => useBoardFilters(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={["/p/x/board"]}>
          {children}
          <Probe />
        </MemoryRouter>
      ),
    });
    act(() => {
      result.current.setView("issues");
    });
    expect(currentLocation).toContain("view=issues");
    act(() => {
      result.current.setMode("graph");
    });
    expect(currentLocation).toContain("mode=graph");
    act(() => {
      result.current.setMode("board");
    });
    // board is the default — should be elided from the URL
    expect(currentLocation).not.toContain("mode=");
    act(() => {
      result.current.toggleAgent("alice");
    });
    act(() => {
      result.current.toggleAgent("bob");
    });
    // Sets are sorted on serialise — keeps URL stable across the
    // two equally-valid orderings of the same selection.
    expect(currentLocation).toMatch(/agent=alice%2Cbob|agent=alice,bob/);
    act(() => {
      result.current.toggleAgent("alice");
    });
    expect(currentLocation).toMatch(/agent=bob(?!,alice)/);
    act(() => {
      result.current.toggleBlockedInbox();
    });
    expect(currentLocation).toContain("inbox=1");
    act(() => {
      result.current.toggleBlockedInbox();
    });
    expect(currentLocation).not.toContain("inbox=1");
  });

  it("clearAll wipes filter params but preserves view", () => {
    let currentLocation = "";
    function Probe() {
      const loc = useLocation();
      currentLocation = `${loc.pathname}${loc.search}`;
      return null;
    }
    const { result } = renderHook(() => useBoardFilters(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={["/p/x/board?view=issues&agent=alice&inbox=1&blocked=1"]}>
          {children}
          <Probe />
        </MemoryRouter>
      ),
    });
    act(() => {
      result.current.clearAll();
    });
    expect(currentLocation).toContain("view=issues");
    expect(currentLocation).not.toContain("agent=");
    expect(currentLocation).not.toContain("inbox=1");
    expect(currentLocation).not.toContain("blocked=1");
  });
});

describe("ageBucket", () => {
  it("buckets by elapsed time", () => {
    const minutesAgo = (n: number) => new Date(Date.now() - n * 60 * 1000).toISOString();
    expect(ageBucket(minutesAgo(30))).toBe("today");
    expect(ageBucket(minutesAgo(60 * 24 * 3))).toBe("this-week");
    expect(ageBucket(minutesAgo(60 * 24 * 14))).toBe("this-month");
    expect(ageBucket(minutesAgo(60 * 24 * 60))).toBe("older");
    expect(ageBucket(null)).toBe("unknown");
  });
});
