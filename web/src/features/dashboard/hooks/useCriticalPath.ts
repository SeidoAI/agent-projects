import { sessionStageId } from "@/components/ui/session-stage-row";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";

/**
 * Critical path computation for the dashboard spine.
 *
 * The "critical path" is the longest dependency chain through
 * in-flight sessions, weighted by downstream fan-out at each node.
 * It answers the highest-leverage PM question: "what should I
 * unblock first?" — i.e. which one piece of work is gating the most
 * downstream sessions and so determines the project's wall time.
 *
 * In-flight = stage ∈ {planned, queued, executing, in_review}.
 * Verified / completed / off-track sessions are excluded from the
 * graph: a path can't pass through finished or stuck nodes for
 * "what to unblock next" purposes.
 *
 * Edges: a session B that has A in `blocked_by_sessions` becomes
 * an edge A → B. Walking forward from a leaf-blocker (no inbound
 * edges in the in-flight subgraph) gives a chain whose length is
 * the depth of work behind it.
 */
const IN_FLIGHT_STAGES = new Set(["planned", "queued", "executing", "in_review"]);

export interface CriticalPathResult {
  /** Ordered chain from earliest-blocker to latest. */
  chain: SessionSummary[];
  /** Sessions blocked transitively by the chain head, including chain
   *  members themselves. Used for the "blocks N downstream" subtitle. */
  fanout: number;
  /** True when multiple chains tie on length+fanout. The renderer
   *  surfaces this with a footnote. */
  tied: boolean;
  /** Total number of in-flight sessions considered. Used to render
   *  the all-independent / empty-graph empty state. */
  inFlightCount: number;
  /** Per-chain-node count of in-flight sessions that this node
   *  directly blocks (i.e. they list this node in
   *  `blocked_by_sessions`). Includes the chain successor — so
   *  the badge total matches what the right-column blocker
   *  filter shows when the chip is clicked. Keyed by session id. */
  directUnlocks: Record<string, number>;
}

/** Pure function — easier to unit test than the wrapping hook. */
export function computeCriticalPath(sessions: SessionSummary[]): CriticalPathResult {
  const inFlight = sessions.filter((s) => {
    const stageId = sessionStageId(s.status);
    return stageId !== null && IN_FLIGHT_STAGES.has(stageId);
  });
  const inFlightIds = new Set(inFlight.map((s) => s.id));
  const byId = new Map(inFlight.map((s) => [s.id, s] as const));

  // Forward edges: blocker → blocked. We only track edges between
  // in-flight sessions (an edge to a verified blocker would imply
  // the blocker is done — not useful for "what to unblock next").
  const forward = new Map<string, string[]>();
  for (const session of inFlight) {
    for (const blockerId of session.blocked_by_sessions) {
      if (!inFlightIds.has(blockerId)) continue;
      const arr = forward.get(blockerId);
      if (arr) arr.push(session.id);
      else forward.set(blockerId, [session.id]);
    }
  }

  // For each in-flight session, compute (a) longest chain starting
  // from it and (b) total transitive fan-out behind it. The longest
  // chain is memoised; fan-out runs a per-call BFS so it can dedup
  // converging branches without producing path-dependent caches.
  const longestChainCache = new Map<string, string[]>();
  const stack = new Set<string>(); // cycle guard for longestFrom

  function longestFrom(id: string): string[] {
    const cached = longestChainCache.get(id);
    if (cached) return cached;
    // Cycle detected: stop walking forward without extending the
    // chain (the caller will still prepend its own id). Returning
    // [id] here would duplicate the cycled node in the result.
    if (stack.has(id)) return [];
    stack.add(id);
    let best: string[] = [];
    for (const next of forward.get(id) ?? []) {
      const candidate = longestFrom(next);
      if (candidate.length > best.length) best = candidate;
    }
    stack.delete(id);
    const result = [id, ...best];
    longestChainCache.set(id, result);
    return result;
  }

  // BFS over downstream descendants, counting each unique node
  // exactly once. The recursive variant double-counted converging
  // branches in diamond DAGs (A→B→D + A→C→D would charge D twice
  // to A's score), inflating the spine subtitle and skewing
  // tie-breaking between candidate roots. The visited-set is also
  // a natural cycle guard, so the older `stack` mechanism isn't
  // needed for this function (`longestFrom` still uses it).
  // Per-id caching is dropped because the cached value would be
  // incorrect when the set of already-visited nodes differs
  // between callers.
  function fanoutFrom(id: string): number {
    const visited = new Set<string>([id]);
    const queue: string[] = [id];
    while (queue.length > 0) {
      const cur = queue.shift() as string;
      for (const next of forward.get(cur) ?? []) {
        if (!visited.has(next)) {
          visited.add(next);
          queue.push(next);
        }
      }
    }
    // -1 to exclude the root itself; we want "nodes downstream of id".
    return visited.size - 1;
  }

  // Candidate chains start at "roots": in-flight sessions whose
  // blockers are all outside the in-flight subgraph (i.e. they
  // could start work right now if other constraints permit). If a
  // dependency cycle leaves no true roots, fall back to scanning
  // every in-flight session — the cycle guard caps recursion.
  const incoming = new Map<string, number>();
  for (const arr of forward.values()) {
    for (const id of arr) incoming.set(id, (incoming.get(id) ?? 0) + 1);
  }
  let roots = inFlight.filter((s) => (incoming.get(s.id) ?? 0) === 0);
  if (roots.length === 0) roots = inFlight;

  let bestChain: string[] = [];
  let bestFanout = 0;
  let bestCount = 0;
  for (const root of roots) {
    const chain = longestFrom(root.id);
    const fan = fanoutFrom(root.id);
    if (
      chain.length > bestChain.length ||
      (chain.length === bestChain.length && fan > bestFanout)
    ) {
      bestChain = chain;
      bestFanout = fan;
      bestCount = 1;
    } else if (chain.length === bestChain.length && fan === bestFanout) {
      bestCount += 1;
    }
  }

  // Per-chain-node total direct unlocks: every in-flight session
  // that lists this node in `blocked_by_sessions`, including the
  // chain successor. The badge in the spine + the right-column
  // blocker filter both consume this — keeping them aligned
  // makes the count match the filtered list. Only computed when
  // the chain is real (≥2 nodes); the renderer collapses
  // otherwise and doesn't read this map.
  const directUnlocks: Record<string, number> = {};
  if (bestChain.length >= 2) {
    for (const id of bestChain) {
      directUnlocks[id] = (forward.get(id) ?? []).length;
    }
  }

  return {
    chain: bestChain.map((id) => byId.get(id)).filter((s): s is SessionSummary => Boolean(s)),
    fanout: bestFanout,
    tied: bestCount > 1,
    inFlightCount: inFlight.length,
    directUnlocks,
  };
}
