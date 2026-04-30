import { useEffect, useMemo, useRef, useState } from "react";

import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import { type SessionSummary, useSessions } from "@/lib/api/endpoints/sessions";
import { SessionCard } from "./SessionCard";
import { SessionFlow } from "./SessionFlow";
import { colorForStatus, statusOrder, statusStyle } from "./sessionStatus";

const ACTIONABLE_BLOCKED_STATUS = "planned";

function isActionable(session: SessionSummary, statusIndex: Map<string, string>): boolean {
  if (session.status !== ACTIONABLE_BLOCKED_STATUS) return true;
  if (session.blocked_by_sessions.length === 0) return true;
  return session.blocked_by_sessions.every((blocker) => {
    const s = statusIndex.get(blocker);
    return s === "completed" || s === "reviewing";
  });
}

export function SessionList() {
  const { projectId } = useProjectShell();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [onlyActionable, setOnlyActionable] = useState(false);
  const [showAllCompletedInFlow, setShowAllCompletedInFlow] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);
  const { data, isLoading, error } = useSessions(projectId, statusFilter || undefined);
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const statusIndex = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of data ?? []) map.set(s.id, s.status);
    return map;
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!onlyActionable) return data;
    return data.filter((s) => isActionable(s, statusIndex));
  }, [data, onlyActionable, statusIndex]);

  const allStatuses = useMemo(() => {
    const set = new Set<string>();
    for (const s of data ?? []) set.add(s.status);
    return Array.from(set).sort();
  }, [data]);

  /** Sort by (status, name) and keep the per-status buckets together. */
  const grouped = useMemo(() => {
    const buckets = new Map<string, SessionSummary[]>();
    for (const s of filtered) {
      if (!buckets.has(s.status)) buckets.set(s.status, []);
      buckets.get(s.status)!.push(s);
    }
    const sortedKeys = Array.from(buckets.keys()).sort(
      (a, b) => statusOrder(a) - statusOrder(b) || a.localeCompare(b),
    );
    return sortedKeys.map((status) => {
      const list = buckets.get(status)!;
      list.sort((a, b) => {
        // Within "planned": actionable first.
        if (status === "planned") {
          const aa = isActionable(a, statusIndex) ? 0 : 1;
          const bb = isActionable(b, statusIndex) ? 0 : 1;
          if (aa !== bb) return aa - bb;
        }
        return a.name.localeCompare(b.name);
      });
      return { status, sessions: list };
    });
  }, [filtered, statusIndex]);

  // Default focus on the first executing session once data lands.
  useEffect(() => {
    if (focusId !== null) return;
    if (!data || data.length === 0) return;
    const exec = data.find((s) => statusOrder(s.status) === 0);
    if (exec) setFocusId(exec.id);
  }, [data, focusId]);

  // Scroll focused card into view (smooth) when focus changes.
  useEffect(() => {
    if (!focusId) return;
    const el = cardRefs.current.get(focusId);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId]);

  if (isLoading) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-5 w-40" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-sm text-red-500" role="alert">
        Failed to load sessions.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-8">
      <header className="flex flex-col gap-1">
        <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          chapter 06 · sessions
        </div>
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) leading-tight tracking-[-0.02em]">
          Sessions
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2)">
          Dependencies flow top-down; cards are grouped by status.
        </p>
      </header>

      {/* Graph controls — affect the flow above only. */}
      {filtered.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 border-(--color-edge) border-b pb-3">
          <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            graph
          </span>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={showAllCompletedInFlow}
              onChange={(e) => setShowAllCompletedInFlow(e.target.checked)}
            />
            Show all completed in graph
          </label>
        </div>
      )}

      {filtered.length > 0 && (
        <SessionFlow
          sessions={filtered}
          focusId={focusId}
          onSelect={setFocusId}
          showAllCompleted={showAllCompletedInFlow}
        />
      )}

      {/* Card controls — affect the grouped list below. */}
      {filtered.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-3 border-(--color-edge) border-b pb-3">
          <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            cards
          </span>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>status:</span>
            <select
              className="rounded border bg-background px-2 py-1 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Filter sessions by status"
            >
              <option value="">all</option>
              {allStatuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={onlyActionable}
              onChange={(e) => setOnlyActionable(e.target.checked)}
            />
            Only actionable
          </label>
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No sessions yet. The PM agent creates sessions during scoping.
        </p>
      ) : (
        <div className="flex flex-col gap-6" data-testid="session-grid">
          {grouped.map(({ status, sessions }) => (
            <section key={status} aria-label={`${status} sessions`}>
              <div className="mb-3 flex items-center gap-3">
                <span
                  aria-hidden
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: colorForStatus(status) }}
                />
                <h2 className="font-mono text-[11px] text-(--color-ink-2) uppercase tracking-[0.18em]">
                  {statusStyle(status).label}
                </h2>
                <span className="font-mono text-[11px] text-(--color-ink-3) tabular-nums">
                  {sessions.length}
                </span>
                <span
                  aria-hidden
                  className="ml-1 h-px flex-1 bg-(--color-edge)"
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    ref={(el) => {
                      if (el) cardRefs.current.set(session.id, el);
                      else cardRefs.current.delete(session.id);
                    }}
                  >
                    <SessionCard
                      session={session}
                      projectId={projectId}
                      isFocused={session.id === focusId}
                    />
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
