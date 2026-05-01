import { describe, expect, it } from "vitest";

import { computeCriticalPath } from "@/features/dashboard/hooks/useCriticalPath";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";

function sess(id: string, status: string, blockedBy: string[] = []): SessionSummary {
  return {
    id,
    name: id,
    agent: "test-agent",
    status,
    issues: [],
    estimated_size: null,
    blocked_by_sessions: blockedBy,
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    cost_usd: 0,
  };
}

describe("computeCriticalPath", () => {
  it("returns an empty chain when no sessions exist", () => {
    const result = computeCriticalPath([]);
    expect(result.chain).toEqual([]);
    expect(result.inFlightCount).toBe(0);
    expect(result.tied).toBe(false);
  });

  it("returns an empty chain when no sessions are in flight", () => {
    // verified + completed + off-track sessions are excluded — the
    // critical path is only meaningful for live work.
    const result = computeCriticalPath([
      sess("a", "verified"),
      sess("b", "completed"),
      sess("c", "failed"),
    ]);
    expect(result.chain).toEqual([]);
    expect(result.inFlightCount).toBe(0);
  });

  it("returns a single-node chain when one in-flight session exists", () => {
    // chain.length === 1 — the renderer surfaces this as "no chain
    // — 1 independent session running" so the ambient signal is
    // still meaningful.
    const result = computeCriticalPath([sess("a", "executing")]);
    expect(result.chain.map((s) => s.id)).toEqual(["a"]);
    expect(result.inFlightCount).toBe(1);
  });

  it("walks the longest linear chain through in-flight sessions", () => {
    // a → b → c → d (all in-flight). Should pick the full 4-deep
    // chain over any shorter path.
    const result = computeCriticalPath([
      sess("a", "planned"),
      sess("b", "queued", ["a"]),
      sess("c", "executing", ["b"]),
      sess("d", "in_review", ["c"]),
    ]);
    expect(result.chain.map((s) => s.id)).toEqual(["a", "b", "c", "d"]);
    expect(result.inFlightCount).toBe(4);
  });

  it("excludes verified sessions from the chain even if they're blockers", () => {
    // a (verified) → b (executing) → c (in_review). The path
    // starts at b — verified sessions don't block anything.
    const result = computeCriticalPath([
      sess("a", "verified"),
      sess("b", "executing", ["a"]),
      sess("c", "in_review", ["b"]),
    ]);
    expect(result.chain.map((s) => s.id)).toEqual(["b", "c"]);
    expect(result.inFlightCount).toBe(2);
  });

  it("breaks ties on length by preferring higher fan-out", () => {
    // Two chains of equal length:
    //   a → b   (fanout: 1)
    //   c → d, c → e (fanout: 2 — c blocks both d and e)
    //
    // The critical-path computation prefers chains that block more
    // downstream work. Expected winner: chain through c.
    const result = computeCriticalPath([
      sess("a", "planned"),
      sess("b", "queued", ["a"]),
      sess("c", "planned"),
      sess("d", "queued", ["c"]),
      sess("e", "queued", ["c"]),
    ]);
    // Both chains have length 2, but c has fanout=2 (blocks d+e),
    // a has fanout=1 (blocks only b).
    expect(result.chain[0]?.id).toBe("c");
    expect(result.chain.length).toBe(2);
    expect(result.fanout).toBe(2);
  });

  it("flags ties when multiple chains have identical length and fanout", () => {
    // Two perfectly mirrored chains: a→b and c→d, each fanout=1.
    const result = computeCriticalPath([
      sess("a", "planned"),
      sess("b", "queued", ["a"]),
      sess("c", "planned"),
      sess("d", "queued", ["c"]),
    ]);
    expect(result.chain.length).toBe(2);
    expect(result.tied).toBe(true);
  });

  it("reports inFlightCount even when there's no chain to render", () => {
    // 5 fully-independent sessions. Renderer uses inFlightCount for
    // "no critical path — 5 independent sessions running".
    const result = computeCriticalPath([
      sess("a", "executing"),
      sess("b", "executing"),
      sess("c", "executing"),
      sess("d", "in_review"),
      sess("e", "queued"),
    ]);
    expect(result.chain.length).toBeLessThanOrEqual(1);
    expect(result.inFlightCount).toBe(5);
  });

  it("counts total direct unlocks per chain node, including the chain successor", () => {
    // Chain: a → b → c (longest, fanout 2).
    // a also blocks d (a parallel branch).
    // b also blocks e (another parallel branch).
    //
    // Direct unlocks should be: a → 2 (b + d), b → 2 (c + e),
    // c → 0. The chain successor IS counted so the badge total
    // matches what the right-column blocker filter shows on
    // click ("blocker + N blocked").
    const result = computeCriticalPath([
      sess("a", "planned"),
      sess("b", "queued", ["a"]),
      sess("c", "executing", ["b"]),
      sess("d", "queued", ["a"]),
      sess("e", "queued", ["b"]),
    ]);
    expect(result.chain.map((s) => s.id)).toEqual(["a", "b", "c"]);
    expect(result.directUnlocks).toEqual({ a: 2, b: 2, c: 0 });
  });

  it("returns an empty directUnlocks map when there's no chain", () => {
    const result = computeCriticalPath([sess("a", "executing"), sess("b", "executing")]);
    expect(result.directUnlocks).toEqual({});
  });

  it("deduplicates fan-out across diamond dependencies", () => {
    // Diamond: a → b, a → c, b → d, c → d.
    // d is reachable through both branches. The fanout score for
    // a should count d once (unique downstream nodes = {b, c, d}),
    // not twice (which a naive recursive sum would produce —
    // counting d via b AND via c). Without dedup the spine
    // subtitle would over-state how much the chain unblocks and
    // ties between candidate roots could resolve incorrectly.
    const result = computeCriticalPath([
      sess("a", "planned"),
      sess("b", "queued", ["a"]),
      sess("c", "queued", ["a"]),
      sess("d", "executing", ["b", "c"]),
    ]);
    // a is the only root. Longest chain is a → b → d (or a → c → d),
    // length 3. Fan-out is unique downstream count = 3 (b, c, d),
    // not 4 (which would be the naive double-counted total).
    expect(result.chain[0]?.id).toBe("a");
    expect(result.chain.length).toBe(3);
    expect(result.fanout).toBe(3);
  });

  it("doesn't loop forever on a dependency cycle", () => {
    // Corrupt-data defence: a → b → a. The algorithm breaks the
    // cycle and returns a finite chain rather than hanging.
    const result = computeCriticalPath([
      sess("a", "executing", ["b"]),
      sess("b", "executing", ["a"]),
    ]);
    expect(result.chain.length).toBeGreaterThan(0);
    expect(result.chain.length).toBeLessThanOrEqual(2);
  });
});
