import { useMemo } from "react";
import { Link } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { LIVE_STATUSES, statusStyle } from "@/features/sessions/sessionStatus";
import {
  type RepoBinding,
  type SessionSummary,
  useSessions,
} from "@/lib/api/endpoints/sessions";
import {
  useWorkflowEvents,
  type WorkflowEvent,
} from "@/lib/api/endpoints/workflowEvents";
import { cn } from "@/lib/utils";

/**
 * Monitor — operator-facing view of work-in-flight.
 *
 * Persona: a human operator watching the PM agent + coding agents
 * collaborate. Distinct from the Board (which is task-oriented:
 * "what should I assign next") and the Quality page (which is
 * retrospective: "where did the process bend"). Monitor answers
 * "what's running right now, and is anything on fire."
 *
 * Stage 1 surface (this file):
 *   - Active-session strip — one row per session in `LIVE_STATUSES`
 *   - Per-row: agent, status, task progress, linked PRs, recent
 *     tripwire fires correlated by `instance` from the events log.
 *
 * Stage 2 (deferred — see [[principle-monitor-as-operational-view]]):
 *   - WS-driven live event stream pane
 *   - Per-engagement cost-burn ticker
 *   - Worktree-scoped fire indicators (`firing in worktree X` chip)
 */
export function Monitor() {
  const { projectId } = useProjectShell();
  const sessionsQuery = useSessions(projectId);
  const eventsQuery = useWorkflowEvents(projectId, {});

  const sessions = sessionsQuery.data ?? [];
  const activeSessions = useMemo(
    () => sessions.filter((s) => LIVE_STATUSES.has(s.status)),
    [sessions],
  );

  const tripwireFiresBySession = useMemo(() => {
    const m = new Map<string, WorkflowEvent[]>();
    for (const e of eventsQuery.data?.events ?? []) {
      // jit_prompt.fired is the canonical "tripwire fired" signal —
      // validators emit even on success, transitions are routine.
      if (e.event !== "jit_prompt.fired") continue;
      const arr = m.get(e.instance) ?? [];
      arr.push(e);
      m.set(e.instance, arr);
    }
    // Newest fire first within each session.
    for (const arr of m.values()) {
      arr.sort((a, b) => b.ts.localeCompare(a.ts));
    }
    return m;
  }, [eventsQuery.data]);

  const totalFires = useMemo(() => {
    let n = 0;
    for (const arr of tripwireFiresBySession.values()) n += arr.length;
    return n;
  }, [tripwireFiresBySession]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Monitor
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          what's in flight right now — for operators watching the PM agent and coding agents
          collaborate.
        </p>
      </header>

      <SummaryStrip
        activeCount={activeSessions.length}
        totalCount={sessions.length}
        tripwireCount={totalFires}
      />

      {activeSessions.length === 0 ? (
        <EmptyState totalSessions={sessions.length} />
      ) : (
        <ul
          className="flex flex-col gap-3"
          data-testid="monitor-active-sessions"
          aria-label="Active sessions"
        >
          {activeSessions.map((session) => (
            <li key={session.id}>
              <ActiveSessionCard
                projectId={projectId}
                session={session}
                recentFires={tripwireFiresBySession.get(session.id) ?? []}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SummaryStrip({
  activeCount,
  totalCount,
  tripwireCount,
}: {
  activeCount: number;
  totalCount: number;
  tripwireCount: number;
}) {
  return (
    <section
      aria-label="Monitor summary"
      data-testid="monitor-summary"
      className="grid grid-cols-3 gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      <Stat label="active" value={activeCount} testId="monitor-stat-active" />
      <Stat label="total sessions" value={totalCount} testId="monitor-stat-total" />
      <Stat
        label="tripwires firing"
        value={tripwireCount}
        testId="monitor-stat-tripwires"
        emphasised={tripwireCount > 0}
      />
    </section>
  );
}

function Stat({
  label,
  value,
  testId,
  emphasised = false,
}: {
  label: string;
  value: number;
  testId: string;
  emphasised?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1" data-testid={testId}>
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        {label}
      </span>
      <span
        className={cn(
          "font-sans font-semibold text-[24px] tabular-nums",
          emphasised ? "text-(--color-rule)" : "text-(--color-ink)",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ActiveSessionCard({
  projectId,
  session,
  recentFires,
}: {
  projectId: string;
  session: SessionSummary;
  recentFires: WorkflowEvent[];
}) {
  const style = statusStyle(session.status);
  const progressPct =
    session.task_progress.total > 0
      ? Math.round((session.task_progress.done / session.task_progress.total) * 100)
      : 0;
  const linkedPrs = session.repos.filter((r) => r.pr_number !== null);
  const lastFire = recentFires[0];

  return (
    <article
      data-testid={`monitor-session-${session.id}`}
      data-fires={recentFires.length}
      className="flex flex-col gap-3 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-4 py-3"
    >
      <header className="flex flex-wrap items-baseline gap-3">
        <Link
          to={`/p/${projectId}/sessions/${session.id}`}
          className="font-mono text-[12px] text-(--color-ink) hover:underline"
        >
          {session.id}
        </Link>
        <h2 className="m-0 font-sans font-medium text-[15px] text-(--color-ink)">
          {session.name}
        </h2>
        <span
          className="rounded-(--radius-stamp) px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em]"
          style={{
            backgroundColor: style.color,
            color: style.textOnFill === "paper" ? "var(--color-paper)" : "var(--color-ink)",
            opacity: style.fillOpacity,
          }}
          data-testid={`monitor-session-${session.id}-status`}
        >
          {style.label}
        </span>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
          agent · {session.agent}
        </span>
      </header>

      <ProgressRow
        done={session.task_progress.done}
        total={session.task_progress.total}
        pct={progressPct}
      />

      <footer className="flex flex-wrap items-center gap-3 border-(--color-edge) border-t pt-2">
        <PrBadges prs={linkedPrs} />
        <TripwireBadge count={recentFires.length} lastFire={lastFire} />
      </footer>
    </article>
  );
}

function ProgressRow({ done, total, pct }: { done: number; total: number; pct: number }) {
  return (
    <div className="flex items-center gap-3" data-testid="monitor-progress">
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        progress
      </span>
      <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-(--color-paper-3)">
        <div
          className="h-full bg-(--color-ink)"
          style={{ width: `${pct}%` }}
          data-testid="monitor-progress-bar"
        />
      </div>
      <span className="font-mono text-[11px] tabular-nums text-(--color-ink)">
        {done} / {total}
      </span>
    </div>
  );
}

function PrBadges({ prs }: { prs: RepoBinding[] }) {
  if (prs.length === 0) {
    return (
      <span
        className="font-mono text-[11px] italic text-(--color-ink-3)"
        data-testid="monitor-prs-none"
      >
        no PRs linked
      </span>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="monitor-prs">
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        PR
      </span>
      {prs.map((r) => (
        <Stamp
          key={`${r.repo}#${r.pr_number}`}
          tone="info"
          variant="identifier"
          data-testid={`monitor-pr-${r.repo}-${r.pr_number}`}
        >
          {r.repo}#{r.pr_number}
        </Stamp>
      ))}
    </div>
  );
}

function TripwireBadge({ count, lastFire }: { count: number; lastFire: WorkflowEvent | undefined }) {
  if (count === 0) {
    return (
      <span
        className="ml-auto font-mono text-[11px] italic text-(--color-ink-3)"
        data-testid="monitor-tripwires-none"
      >
        no tripwires firing
      </span>
    );
  }
  return (
    <span
      className="ml-auto flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-2 py-1 font-mono text-[11px] text-(--color-rule)"
      data-testid="monitor-tripwires"
    >
      <span className="font-semibold tabular-nums">{count}</span>
      <span>tripwire{count === 1 ? "" : "s"}</span>
      {lastFire ? (
        <span className="text-(--color-ink-3)" data-testid="monitor-tripwires-last">
          last · {formatTs(lastFire.ts)}
        </span>
      ) : null}
    </span>
  );
}

function EmptyState({ totalSessions }: { totalSessions: number }) {
  return (
    <section
      data-testid="monitor-empty"
      aria-label="No active sessions"
      className="flex flex-1 flex-col items-center justify-center gap-2 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-8"
    >
      <p className="font-sans text-[16px] text-(--color-ink-2)">
        Nothing in flight right now.
      </p>
      <p className="font-serif text-[13px] italic text-(--color-ink-3)">
        {totalSessions === 0
          ? "No sessions exist yet — the PM agent creates them during scoping."
          : `${totalSessions} session${totalSessions === 1 ? "" : "s"} on file, all idle (queued, completed, or paused).`}
      </p>
    </section>
  );
}

function formatTs(ts: string): string {
  const t = ts.split("T")[1];
  return t ? t.replace("Z", "") : ts;
}
