import { Stamp } from "@/components/ui/stamp";
import type { Engagement } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";

/**
 * Vertical list of [[engagement-primitive]] entries on the v0.8
 * Session Detail screen.
 *
 * Each engagement is one start-to-pause cycle of the coding agent.
 * The full timeline of *turns* within an engagement is deferred to
 * TW1-2 (see `sessions/v08-session-detail/plan.md` §"Scope correction —
 * Option C") — for v0.8 we just surface the engagement boundaries
 * themselves, which is enough to distinguish "first attempt" from
 * "re-engagement after pause" when reviewing a session.
 *
 * Open engagements (no `ended_at`) are flagged via `data-active="true"`
 * on the row; closed engagements show their duration.
 */
export interface SessionEngagementListProps {
  engagements: Engagement[];
  className?: string;
}

export function SessionEngagementList({ engagements, className }: SessionEngagementListProps) {
  if (engagements.length === 0) {
    return (
      <p className={cn("font-serif text-[14px] italic text-(--color-ink-3)", className)}>
        no engagements recorded yet — this session has not been spawned.
      </p>
    );
  }

  return (
    <ol className={cn("flex flex-col gap-2", className)}>
      {engagements.map((eng, idx) => (
        <li key={eng.engagement_id ?? `${eng.started_at}-${idx}`}>
          <EngagementRow engagement={eng} index={idx + 1} />
        </li>
      ))}
    </ol>
  );
}

function EngagementRow({ engagement, index }: { engagement: Engagement; index: number }) {
  const isActive = engagement.ended_at === null || engagement.ended_at === undefined;
  const duration = computeDuration(engagement.started_at, engagement.ended_at);

  return (
    <div
      data-testid={`engagement-row-${index}`}
      data-active={String(isActive)}
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-(--radius-stamp) border px-3 py-2",
        isActive
          ? "border-(--color-rule) bg-(--color-rule)/5"
          : "border-(--color-edge) bg-(--color-paper)",
      )}
    >
      <Stamp variant="identifier">engagement #{index}</Stamp>
      {isActive ? (
        <Stamp tone="rule" variant="status">
          active
        </Stamp>
      ) : engagement.outcome ? (
        <Stamp tone={outcomeToTone(engagement.outcome)} variant="status">
          {engagement.outcome}
        </Stamp>
      ) : null}
      {engagement.trigger ? (
        <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
          trigger · {engagement.trigger}
        </span>
      ) : null}
      <span className="font-mono text-[10px] text-(--color-ink-2) tracking-[0.04em]">
        {formatTimestamp(engagement.started_at)}
        {engagement.ended_at ? ` → ${formatTimestamp(engagement.ended_at)}` : " → (running)"}
      </span>
      {duration ? (
        <span className="ml-auto font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
          {duration}
        </span>
      ) : null}
      {engagement.cost_usd !== undefined && engagement.cost_usd !== null ? (
        <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
          ${engagement.cost_usd.toFixed(2)}
        </span>
      ) : null}
    </div>
  );
}

function outcomeToTone(outcome: string): "default" | "gate" | "tripwire" | "rule" {
  if (outcome === "success") return "gate";
  if (outcome === "paused") return "tripwire";
  if (outcome === "failed" || outcome === "abandoned") return "rule";
  return "default";
}

function formatTimestamp(iso: string): string {
  // ISO → "YYYY-MM-DD HH:mm" — readable, fixed width, parses back to
  // Date if anyone cares. Falls back to the raw string when the input
  // doesn't parse so we never silently drop data; in dev we emit a
  // warn so an unrecognised payload shows up in dev tools rather than
  // as a quiet bad value in the UI.
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    if (import.meta.env.DEV) {
      console.warn("SessionEngagementList: failed to parse engagement timestamp", iso);
    }
    return iso;
  }
  return d.toISOString().slice(0, 16).replace("T", " ");
}

function computeDuration(start: string, end: string | null | undefined): string | null {
  if (!end) return null;
  const a = new Date(start).getTime();
  const b = new Date(end).getTime();
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return null;
  const totalMin = Math.round((b - a) / 60000);
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}
