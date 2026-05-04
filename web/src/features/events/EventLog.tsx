import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { useWorkflowEvents, type WorkflowEvent } from "@/lib/api/endpoints/workflowEvents";

/**
 * Event Log viewer (KUI-155 / I2).
 *
 * Read-only chronological surface over the v0.9 events log. Filter
 * chips persist in the URL via ``?event=...&instance=...&status=...``
 * so deep-links survive reload. The log itself is append-only —
 * ``useWorkflowEvents`` polls every 5s; intermediate-state WS bridge
 * is a future follow-up. The right pane shows the full ``details``
 * payload for the selected row.
 *
 * Per the spec, this surface is viewer-only: no transition affordances,
 * no acknowledgements. Operators run actions through the CLI / actions
 * service; this screen is for observability.
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

export function EventLog() {
  const { projectId } = useProjectShell();
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

  const setFilter = (key: "event" | "workflow" | "instance" | "status", value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value && value !== "") next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  };

  // Synthesize a stable per-row id. The events log emits at second
  // granularity, so a single session/status can produce many rows
  // with the same `(workflow, instance, status, event, ts)` tuple
  // — codex P1. We disambiguate by also including `details.id`
  // (pins validator/tripwire fires apart) and, when ties remain,
  // an occurrence-count suffix `|#N`. The events array is the
  // chronological tail of an append-only log; its prefix is stable
  // across polls, so the suffix is reproducible across renders for
  // the same row, keeping the URL `focus` link valid across refetch.
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

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Events
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          chronological log of every validator, tripwire, prompt-check, and transition. Read-only.
        </p>
      </header>

      <FilterStrip
        kind={selectedKind}
        instance={filters.instance ?? ""}
        onKindChange={(v) => setFilter("event", v || null)}
        onInstanceChange={(v) => setFilter("instance", v || null)}
        onClearAll={() => setSearchParams(new URLSearchParams(), { replace: true })}
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
                      onClick={() => setFilter("focus" as never, key)}
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
  // ``2026-04-30T14:00:00Z`` → ``14:00:00`` for compact list display.
  const t = ts.split("T")[1];
  return t ? t.replace("Z", "") : ts;
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
  // Events log doesn't carry an explicit id; derive one from
  // (workflow, instance, status, event, ts, details.id). The
  // base alone may still collide on dense same-second bursts of
  // the same kind/id; the caller appends an occurrence-count
  // suffix to disambiguate (see `keyedEvents` in EventLog).
  const detailsId = (event.details as { id?: string } | null)?.id ?? "";
  return `${event.workflow}|${event.instance}|${event.status}|${event.event}|${event.ts}|${detailsId}`;
}
