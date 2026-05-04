import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { cn } from "@/lib/utils";
import {
  useWorkflowEvents,
  useWorkflowStats,
  type WorkflowEvent,
} from "@/lib/api/endpoints/workflowEvents";

/**
 * Quality screen — folds the v0.9 events log + aggregate stats into
 * one surface. The legacy `/events` page was removed; its filterable
 * stream is the "events" tab here, and the histogram drill-downs
 * switch to it in-page.
 *
 * URL state:
 *   ?tab=stats|events    (default stats)
 *   ?event=<kind>        events tab filter
 *   ?instance=<sid>      events tab filter
 *   ?workflow=<wf>       events tab filter
 *   ?status=<status>     events tab filter
 *   ?focus=<rowKey>      events tab selection
 */
const EVENT_KIND_FILTERS = [
  "validator.run",
  "jit_prompt.fired",
  "prompt_check.invoked",
  "transition.requested",
  "transition.completed",
  "transition.rejected",
  "pm_review.completed",
] as const;

type Tab = "stats" | "events";

export function Quality() {
  const { projectId } = useProjectShell();
  const [searchParams, setSearchParams] = useSearchParams();

  const tab: Tab = searchParams.get("tab") === "events" ? "events" : "stats";

  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    if (next === "stats") params.delete("tab");
    else params.set("tab", next);
    if (next !== "events") params.delete("focus");
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Quality
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          aggregate analytics + the chronological events log — every validator, tripwire,
          prompt-check, and transition.
        </p>
      </header>

      <TabStrip tab={tab} onChange={setTab} />

      <div className="flex min-h-0 flex-1 flex-col">
        {tab === "stats" ? (
          <StatsPanel projectId={projectId} />
        ) : (
          <EventsPanel projectId={projectId} />
        )}
      </div>
    </div>
  );
}

function TabStrip({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  return (
    <fieldset
      aria-label="Quality view"
      data-testid="quality-tabs"
      className="m-0 inline-flex w-fit items-center gap-0 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-0.5"
    >
      <TabButton active={tab === "stats"} onClick={() => onChange("stats")} testId="tab-stats">
        stats
      </TabButton>
      <TabButton active={tab === "events"} onClick={() => onChange("events")} testId="tab-events">
        events
      </TabButton>
    </fieldset>
  );
}

function TabButton({
  active,
  onClick,
  children,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      data-testid={testId}
      className={cn(
        "rounded-(--radius-stamp) px-3 py-1 font-mono text-[11px] tracking-[0.06em] transition-colors",
        active
          ? "bg-(--color-ink) text-(--color-paper)"
          : "text-(--color-ink-3) hover:text-(--color-ink)",
      )}
    >
      {children}
    </button>
  );
}

// ============================================================================
// Stats panel — drill-downs switch the in-page tab + apply a filter.
// ============================================================================

function StatsPanel({ projectId }: { projectId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = useWorkflowStats(projectId, { top_n: 10 });
  const stats = query.data;

  const total = stats?.total ?? 0;
  const byKind = stats?.by_kind ?? {};
  const byInstance = stats?.by_instance ?? {};
  const topRules = stats?.top_rules ?? [];

  const kindRows = Object.entries(byKind).sort((a, b) => b[1] - a[1]);
  const instanceRows = Object.entries(byInstance).sort((a, b) => b[1] - a[1]);

  // Drill-down sets `tab=events` and the filter in a single URL
  // mutation. The parent re-derives its `tab` state from
  // `searchParams.get("tab")` on the next render — calling a
  // separate `setTab` here would race with the URL update because
  // both `setSearchParams` calls would close over the same stale
  // params and the second would clobber the first.
  const drillTo = (key: "event" | "instance", value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", "events");
    next.set(key, value);
    next.delete("focus");
    setSearchParams(next, { replace: false });
  };

  return (
    <div className="flex flex-col gap-4">
      <StatsStrip total={total} kindCount={kindRows.length} sessionCount={instanceRows.length} />
      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="By event kind" testId="pq-by-kind">
          {kindRows.length === 0 ? (
            <Empty>No events yet.</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {kindRows.map(([kind, count]) => (
                <li key={kind}>
                  <button
                    type="button"
                    onClick={() => drillTo("event", kind)}
                    className="flex w-full items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 text-left hover:bg-(--color-paper-3)"
                    data-testid={`pq-kind-${kind}`}
                  >
                    <Stamp tone="rule">{kind}</Stamp>
                    <BarTrack value={count} max={total} />
                    <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
                      {count}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="By session" testId="pq-by-instance">
          {instanceRows.length === 0 ? (
            <Empty>No sessions in events log.</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {instanceRows.slice(0, 12).map(([instance, count]) => (
                <li key={instance}>
                  <button
                    type="button"
                    onClick={() => drillTo("instance", instance)}
                    className="flex w-full items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 text-left hover:bg-(--color-paper-3)"
                    data-testid={`pq-instance-${instance}`}
                  >
                    <span className="truncate font-mono text-[12px] text-(--color-ink)">
                      {instance}
                    </span>
                    <BarTrack value={count} max={total} />
                    <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
                      {count}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Top rules" testId="pq-top-rules">
          {topRules.length === 0 ? (
            <Empty>No rule fires yet.</Empty>
          ) : (
            <ol className="flex flex-col gap-2">
              {topRules.map((rule, idx) => (
                <li
                  key={rule.id}
                  className="flex items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2"
                >
                  <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <span className="truncate font-mono text-[12px] text-(--color-ink)">
                    {rule.id}
                  </span>
                  <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
                    {rule.count}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  );
}

function StatsStrip({
  total,
  kindCount,
  sessionCount,
}: {
  total: number;
  kindCount: number;
  sessionCount: number;
}) {
  return (
    <section
      aria-label="Quality summary"
      className="grid grid-cols-3 gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      <Stat label="total events" value={total} />
      <Stat label="event kinds" value={kindCount} />
      <Stat label="active sessions" value={sessionCount} />
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        {label}
      </span>
      <span className="font-sans font-semibold text-[24px] text-(--color-ink) tabular-nums">
        {value}
      </span>
    </div>
  );
}

function Panel({
  title,
  testId,
  children,
}: {
  title: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      data-testid={testId}
      className="flex min-h-0 flex-col gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
    >
      <h2 className="font-sans font-semibold text-[14px] uppercase tracking-[0.04em] text-(--color-ink-2)">
        {title}
      </h2>
      {children}
    </section>
  );
}

function BarTrack({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="flex h-2 w-32 overflow-hidden rounded-full bg-(--color-paper-3)">
      <div className="h-full bg-(--color-ink)" style={{ width: `${pct}%` }} />
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-2 py-3 font-serif text-[12px] italic text-(--color-ink-3)">{children}</p>;
}

// ============================================================================
// Events panel — the former EventLog body, now embedded as a tab.
// ============================================================================

function EventsPanel({ projectId }: { projectId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(
    () => ({
      workflow: searchParams.get("workflow") ?? undefined,
      instance: searchParams.get("instance") ?? undefined,
      status: searchParams.get("status") ?? undefined,
      event: searchParams.get("event") ?? undefined,
    }),
    [searchParams],
  );

  const selectedKind = filters.event ?? "";

  const query = useWorkflowEvents(projectId, filters);
  const events = query.data?.events ?? [];

  const setFilter = (
    key: "event" | "workflow" | "instance" | "status" | "focus",
    value: string | null,
  ) => {
    const next = new URLSearchParams(searchParams);
    if (value && value !== "") next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  };

  // Per-row id (events log emits at second granularity; the tuple
  // can collide so the suffix `|#N` disambiguates).
  const keyedEvents = useMemo(() => {
    const counts = new Map<string, number>();
    return events.map((event) => {
      const base = synthIdBase(event);
      const n = (counts.get(base) ?? 0) + 1;
      counts.set(base, n);
      const key = n === 1 ? base : `${base}|#${n}`;
      return { event, key };
    });
  }, [events]);

  const selectedId = searchParams.get("focus") ?? null;
  const selected = useMemo(
    () => keyedEvents.find((e) => e.key === selectedId)?.event ?? null,
    [keyedEvents, selectedId],
  );

  const clearAll = () => {
    // Preserve `tab=events` so the panel doesn't switch back to stats.
    const next = new URLSearchParams();
    next.set("tab", "events");
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <FilterStrip
        kind={selectedKind}
        instance={filters.instance ?? ""}
        onKindChange={(v) => setFilter("event", v || null)}
        onInstanceChange={(v) => setFilter("instance", v || null)}
        onClearAll={clearAll}
      />

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_360px] gap-4">
        <section
          aria-label="Events"
          className="min-h-0 overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
          data-testid="event-log-list"
        >
          {query.isPending ? (
            <EmptyRow>Loading events…</EmptyRow>
          ) : events.length === 0 ? (
            <EmptyRow>No events yet — run a session to populate the log.</EmptyRow>
          ) : (
            <ul className="divide-y divide-(--color-edge)">
              {keyedEvents.map(({ event, key }) => {
                const isSelected = key === selectedId;
                return (
                  <li key={key}>
                    <button
                      type="button"
                      onClick={() => setFilter("focus", key)}
                      data-testid="event-row"
                      data-event-kind={event.event}
                      className={
                        "flex w-full items-center gap-3 px-4 py-2 text-left font-mono text-[12px] text-(--color-ink) hover:bg-(--color-paper-3) " +
                        (isSelected ? "bg-(--color-paper-3)" : "")
                      }
                    >
                      <span className="text-(--color-ink-3) tabular-nums">
                        {formatTs(event.ts)}
                      </span>
                      <KindStamp kind={event.event} />
                      <span className="truncate text-(--color-ink-2)">
                        {event.workflow}/{event.instance}
                      </span>
                      <span className="ml-auto truncate text-(--color-ink-3)">
                        {summarize(event)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <aside
          aria-label="Event detail"
          className="min-h-0 overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-4"
          data-testid="event-detail-pane"
        >
          {selected ? (
            <DetailPane event={selected} />
          ) : (
            <p className="font-serif text-[13px] italic text-(--color-ink-3)">
              Select an event to see its full payload.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

function FilterStrip({
  kind,
  instance,
  onKindChange,
  onInstanceChange,
  onClearAll,
}: {
  kind: string;
  instance: string;
  onKindChange: (v: string) => void;
  onInstanceChange: (v: string) => void;
  onClearAll: () => void;
}) {
  return (
    <section
      aria-label="Filters"
      className="flex flex-wrap items-center gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2"
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        kind
      </span>
      <button
        type="button"
        data-testid="filter-kind-all"
        onClick={() => onKindChange("")}
        className={chipClass(kind === "")}
      >
        all
      </button>
      {EVENT_KIND_FILTERS.map((k) => (
        <button
          key={k}
          type="button"
          data-testid={`filter-kind-${k}`}
          onClick={() => onKindChange(k)}
          className={chipClass(kind === k)}
        >
          {k}
        </button>
      ))}
      <span className="ml-3 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-3)">
        instance
      </span>
      <input
        type="text"
        value={instance}
        placeholder="any session…"
        onChange={(e) => onInstanceChange(e.target.value)}
        data-testid="filter-instance"
        className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1 font-mono text-[11px] text-(--color-ink)"
      />
      <button
        type="button"
        onClick={onClearAll}
        data-testid="filter-clear-all"
        className="ml-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-2) hover:bg-(--color-paper-3)"
      >
        clear
      </button>
    </section>
  );
}

function chipClass(active: boolean): string {
  return (
    "rounded-(--radius-stamp) border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] " +
    (active
      ? "border-(--color-ink) bg-(--color-ink) text-(--color-paper)"
      : "border-(--color-edge) bg-(--color-paper) text-(--color-ink-2) hover:bg-(--color-paper-3)")
  );
}

function KindStamp({ kind }: { kind: string }) {
  const tone =
    kind === "jit_prompt.fired" || kind.endsWith("rejected")
      ? "tripwire"
      : kind.startsWith("validator")
        ? "gate"
        : kind.startsWith("transition")
          ? "rule"
          : "info";
  return <Stamp tone={tone}>{kind}</Stamp>;
}

function DetailPane({ event }: { event: WorkflowEvent }) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="font-sans font-semibold text-[16px] text-(--color-ink)">{event.event}</h2>
      <dl className="grid grid-cols-[80px_1fr] gap-x-3 gap-y-1 font-mono text-[12px] text-(--color-ink-2)">
        <dt>ts</dt>
        <dd className="text-(--color-ink)">{event.ts}</dd>
        <dt>workflow</dt>
        <dd className="text-(--color-ink)">{event.workflow}</dd>
        <dt>instance</dt>
        <dd className="text-(--color-ink)">{event.instance}</dd>
        <dt>status</dt>
        <dd className="text-(--color-ink)">{event.status}</dd>
      </dl>
      <pre
        data-testid="event-detail-json"
        className="overflow-auto rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) p-3 font-mono text-[11px] text-(--color-ink)"
      >
        {JSON.stringify(event.details, null, 2)}
      </pre>
    </div>
  );
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return <p className="px-4 py-6 font-serif text-[13px] italic text-(--color-ink-3)">{children}</p>;
}

function formatTs(ts: string): string {
  // Operator-facing event log: append UTC so the chronological list
  // can't be misread as local time at a glance.
  const t = ts.split("T")[1];
  return t ? `${t.replace("Z", "")} UTC` : ts;
}

function summarize(event: WorkflowEvent): string {
  const d = event.details ?? {};
  const id = (d as { id?: string }).id;
  if (id) return `${event.status} · ${id}`;
  const reason = (d as { reason?: string }).reason;
  if (reason) return `${event.status} · ${reason}`;
  const outcome = (d as { outcome?: string }).outcome;
  if (outcome) return `${event.status} · ${outcome}`;
  return event.status;
}

function synthIdBase(event: WorkflowEvent): string {
  const detailsId = (event.details as { id?: string } | null)?.id ?? "";
  return `${event.workflow}|${event.instance}|${event.status}|${event.event}|${event.ts}|${detailsId}`;
}
