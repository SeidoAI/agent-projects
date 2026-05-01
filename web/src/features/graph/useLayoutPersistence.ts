import { useEffect, useMemo, useRef } from "react";

import { type ConceptLayoutEntry, graphApi } from "@/lib/api/endpoints/graph";

type NodeLayout = ConceptLayoutEntry;

const DEBOUNCE_MS = 1500;

/**
 * Buffers per-node (x, y) updates and flushes them as a single batched
 * PATCH to `/api/projects/{pid}/graph/concept/layout` after the canvas
 * settles.
 *
 * The Concept Graph (KUI-104) seeds positions with d3-force on first
 * load. As the simulation ticks we accumulate the latest position per
 * node, then debounce a flush to the backend so reloads don't re-shuffle
 * the canvas. The batched PATCH writes the project's
 * `.tripwire/concept-layout.json` sidecar — never node YAMLs — so the
 * file watcher does not classify the write as a node change. That's
 * what prevents the self-amplifying re-seed loop the previous per-node
 * PATCH design suffered from.
 */
export interface UseLayoutPersistence {
  /** Buffer one or more node positions for eventual persistence. */
  persist: (positions: Record<string, NodeLayout>) => void;
  /** Force an immediate flush — used on unmount / explicit save. */
  flush: () => Promise<void>;
}

export function useLayoutPersistence(projectId: string): UseLayoutPersistence {
  const pendingRef = useRef<Map<string, NodeLayout>>(new Map());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tracks the project id that owns the *current* buffer. We pin
  // it at persist time (and again when projectId changes through a
  // synchronous flush) so the eventual PATCH always goes to the
  // project that produced the position. PM #25 round 3 P1: React
  // Router keeps the same component instance across `/p/:pid`
  // changes, so a debounced batch from project A can otherwise
  // dispatch against project B.
  const bufferOwnerRef = useRef<string>(projectId);

  const flush = useMemo(() => {
    return async (): Promise<void> => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      const batch = pendingRef.current;
      if (batch.size === 0) return;
      pendingRef.current = new Map();
      const pid = bufferOwnerRef.current;
      const layouts = Object.fromEntries(batch);
      // One HTTP call. A failure doesn't block subsequent persistence
      // attempts; the next debounce window will retry anything the
      // canvas re-emits.
      try {
        await graphApi.updateConceptLayout(pid, layouts);
      } catch {
        // swallow — see comment above
      }
    };
  }, []);

  // When the route's projectId changes, synchronously flush the
  // pending batch to the OLD project before the new one starts
  // collecting. The empty-batch fast path inside flush() means
  // this is a no-op when there's nothing pending.
  useEffect(() => {
    if (bufferOwnerRef.current === projectId) return;
    void flush();
    bufferOwnerRef.current = projectId;
  }, [projectId, flush]);

  useEffect(() => {
    return () => {
      // Don't drop the pending batch on unmount — flushing here is
      // the only thing that prevents data loss when the user
      // navigates away within the debounce window. Cancel the
      // timer first so flush() doesn't compete with it.
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      void flush();
    };
  }, [flush]);

  const persist = useMemo(() => {
    return (positions: Record<string, NodeLayout>): void => {
      for (const [nid, pos] of Object.entries(positions)) {
        pendingRef.current.set(nid, pos);
      }
      if (timerRef.current !== null) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void flush();
      }, DEBOUNCE_MS);
    };
  }, [flush]);

  return useMemo(() => ({ persist, flush }), [persist, flush]);
}
