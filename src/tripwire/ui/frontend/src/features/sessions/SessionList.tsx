import { useMemo, useState } from "react";
import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import { type SessionSummary, useSessions } from "@/lib/api/endpoints/sessions";
import { SessionCard } from "./SessionCard";

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
  const { data, isLoading, error } = useSessions(projectId, statusFilter || undefined);

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
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-foreground">Sessions</h1>
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

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No sessions yet. The PM agent creates sessions during scoping.
        </p>
      ) : (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="session-grid"
        >
          {filtered.map((session) => (
            <SessionCard key={session.id} session={session} projectId={projectId} />
          ))}
        </div>
      )}
    </div>
  );
}
