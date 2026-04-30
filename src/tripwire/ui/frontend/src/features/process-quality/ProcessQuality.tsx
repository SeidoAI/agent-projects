import { Link } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { useWorkflowStats } from "@/lib/api/endpoints/workflowEvents";

/**
 * Process-Quality screen (KUI-156 / I3).
 *
 * Aggregates the v0.9 events log into:
 *
 *   - per-event-kind histogram (validator.run vs tripwire.fired vs ...)
 *   - per-instance fire histogram (which sessions are noisiest)
 *   - top-N rules table (which validator/tripwire fires most)
 *
 * Drill-down: clicking a row in either histogram navigates to the
 * Event Log filtered to that slice (cross-link to KUI-155).
 */
export function ProcessQuality() {
  const { projectId } = useProjectShell();
  const query = useWorkflowStats(projectId, { top_n: 10 });
  const stats = query.data;

  const total = stats?.total ?? 0;
  const byKind = stats?.by_kind ?? {};
  const byInstance = stats?.by_instance ?? {};
  const topRules = stats?.top_rules ?? [];

  const kindRows = Object.entries(byKind).sort((a, b) => b[1] - a[1]);
  const instanceRows = Object.entries(byInstance).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) tracking-[-0.02em] leading-tight">
          Process quality
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          aggregate analytics over the workflow events log — fire histograms,
          top-N rules, drill-down by kind or session.
        </p>
      </header>

      <StatsStrip total={total} kindCount={kindRows.length} sessionCount={instanceRows.length} />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="By event kind" testId="pq-by-kind">
          {kindRows.length === 0 ? (
            <Empty>No events yet.</Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {kindRows.map(([kind, count]) => (
                <li key={kind}>
                  <Link
                    to={`../events?event=${encodeURIComponent(kind)}`}
                    className="flex items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 hover:bg-(--color-paper-3)"
                    data-testid={`pq-kind-${kind}`}
                  >
                    <Stamp tone="rule">{kind}</Stamp>
                    <BarTrack value={count} max={total} />
                    <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
                      {count}
                    </span>
                  </Link>
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
                  <Link
                    to={`../events?instance=${encodeURIComponent(instance)}`}
                    className="flex items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 hover:bg-(--color-paper-3)"
                    data-testid={`pq-instance-${instance}`}
                  >
                    <span className="truncate font-mono text-[12px] text-(--color-ink)">
                      {instance}
                    </span>
                    <BarTrack value={count} max={total} />
                    <span className="ml-auto font-mono text-[12px] tabular-nums text-(--color-ink)">
                      {count}
                    </span>
                  </Link>
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
                <li key={rule.id} className="flex items-center gap-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2">
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
      aria-label="Process quality summary"
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
      <div
        className="h-full bg-(--color-ink)"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-2 py-3 font-serif text-[12px] italic text-(--color-ink-3)">
      {children}
    </p>
  );
}
