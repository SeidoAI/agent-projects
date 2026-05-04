import { useEffect, useMemo, useState } from "react";

import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { SessionFlow } from "@/features/sessions/SessionFlow";
import { statusOrder } from "@/features/sessions/sessionStatus";

export interface SessionsGraphViewProps {
  sessions: SessionSummary[];
  /** Fired when a node is clicked; the parent opens its preview drawer. */
  onNodeClick: (session: SessionSummary) => void;
}

/**
 * Sessions × Graph quadrant of the Board 2x2 matrix. Wraps the
 * shared `SessionFlow` SVG (the layered DAG that used to live on
 * the deleted `/sessions` page) with the controls that page owned —
 * focus state + the "show all completed" toggle that un-culls
 * far-from-live sessions.
 *
 * Filter state for the underlying session list is owned by `Board`
 * (via `useBoardFilters`), so this component receives the already-
 * filtered set and only manages local UI state.
 */
export function SessionsGraphView({ sessions, onNodeClick }: SessionsGraphViewProps) {
  const [showAllCompleted, setShowAllCompleted] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);

  // Auto-focus the first executing session once data is present.
  // The empty -> non-empty transition happens after the parent's
  // `useSessions` resolves, so we re-run when the array changes.
  useEffect(() => {
    if (focusId !== null) return;
    if (sessions.length === 0) return;
    const exec = sessions.find((s) => statusOrder(s.status) === 0);
    if (exec) setFocusId(exec.id);
  }, [sessions, focusId]);

  const sessionsById = useMemo(() => {
    const m = new Map<string, SessionSummary>();
    for (const s of sessions) m.set(s.id, s);
    return m;
  }, [sessions]);

  return (
    <div
      className="flex h-full min-h-0 flex-col gap-3"
      data-testid="sessions-graph-view"
    >
      <div className="flex flex-wrap items-center gap-3 border-(--color-edge) border-b pb-3">
        <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          graph
        </span>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            data-testid="sessions-graph-show-all-completed"
            checked={showAllCompleted}
            onChange={(e) => setShowAllCompleted(e.target.checked)}
          />
          Show all completed in graph
        </label>
      </div>

      {sessions.length === 0 ? (
        <p className="px-1 py-4 font-serif text-[12px] text-(--color-ink-3) italic">
          No sessions match the current filters.
        </p>
      ) : (
        <SessionFlow
          sessions={sessions}
          focusId={focusId}
          onSelect={(id) => {
            setFocusId(id);
            const s = sessionsById.get(id);
            if (s) onNodeClick(s);
          }}
          showAllCompleted={showAllCompleted}
        />
      )}
    </div>
  );
}
