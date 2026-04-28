import { useEffect, useMemo, useRef } from "react";

import { type NodeLayout, nodesApi } from "@/lib/api/endpoints/nodes";

const DEBOUNCE_MS = 1500;

/**
 * Buffers per-node (x, y) updates and PATCHes them to
 * `/api/projects/{pid}/nodes/{id}/layout` after the canvas settles.
 *
 * The Concept Graph (KUI-104) seeds positions with d3-force on first
 * load. As the simulation ticks we accumulate the latest position
 * per node, then debounce a flush to the backend so reload doesn't
 * re-shuffle the canvas. One PATCH per distinct node id; only the
 * last position in a debounce window is sent.
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
  const projectRef = useRef(projectId);
  projectRef.current = projectId;

  const flush = useMemo(() => {
    return async (): Promise<void> => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      const batch = pendingRef.current;
      if (batch.size === 0) return;
      pendingRef.current = new Map();
      const pid = projectRef.current;
      // Fire-and-forget per node; failures don't block subsequent
      // persistence attempts. The next debounce window will retry
      // anything the canvas re-emits.
      await Promise.allSettled(
        Array.from(batch.entries()).map(([nid, layout]) => nodesApi.updateLayout(pid, nid, layout)),
      );
    };
  }, []);

  useEffect(() => {
    return () => {
      // Drop any pending timer on unmount; we don't need the result.
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

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

  return { persist, flush };
}
