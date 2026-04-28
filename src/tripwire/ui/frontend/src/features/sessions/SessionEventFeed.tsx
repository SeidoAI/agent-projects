import { useMemo, useState } from "react";

import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { Stamp, type StampTone } from "@/components/ui/stamp";
import {
  type ProcessEvent,
  type ProcessEventKind,
  useSessionEvents,
} from "@/lib/api/endpoints/events";
import { cn } from "@/lib/utils";

/**
 * Per-session filtered ProcessEvent feed (KUI-100). Replaces the
 * deferred turn timeline on the v0.8 Session Detail screen — see
 * `sessions/v08-session-detail/plan.md` §"Scope correction — Option C".
 *
 * Layout: a row of five chip filters (mapping to the five canonical
 * kind buckets — see `KIND_BUCKETS` below) + a vertical list of event
 * rows, newest-first. Each row renders the timestamp + kind badge +
 * a short label sourced from kind-specific fields. Long event payloads
 * expand into the shared `EntityPreviewDrawer` for review.
 */
export interface SessionEventFeedProps {
  projectId: string;
  sessionId: string;
  className?: string;
}

interface KindBucket {
  id: string;
  label: string;
  kinds: ProcessEventKind[];
}

const KIND_BUCKETS: KindBucket[] = [
  { id: "firings", label: "firings", kinds: ["tripwire_fire"] },
  {
    id: "validator_runs",
    label: "validator runs",
    kinds: ["validator_pass", "validator_fail"],
  },
  { id: "rejections", label: "rejections", kinds: ["artifact_rejected"] },
  {
    id: "pm_reviews",
    label: "pm reviews",
    kinds: ["pm_review_opened", "pm_review_closed"],
  },
  {
    id: "status_transitions",
    label: "status transitions",
    kinds: ["status_transition"],
  },
];

export function SessionEventFeed({ projectId, sessionId, className }: SessionEventFeedProps) {
  const [activeBucket, setActiveBucket] = useState<string | null>(null);
  const [expandedEvent, setExpandedEvent] = useState<ProcessEvent | null>(null);

  const kinds = useMemo(() => {
    if (!activeBucket) return undefined;
    return KIND_BUCKETS.find((b) => b.id === activeBucket)?.kinds;
  }, [activeBucket]);

  const { data, isLoading, isError } = useSessionEvents(projectId, sessionId, { kinds });

  const events = data?.events ?? [];

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap gap-1.5" data-testid="event-filter-chips">
        {KIND_BUCKETS.map((bucket) => {
          const active = activeBucket === bucket.id;
          return (
            <button
              key={bucket.id}
              type="button"
              onClick={() => setActiveBucket(active ? null : bucket.id)}
              aria-pressed={active}
              className={cn(
                "rounded-(--radius-stamp) border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.06em] transition-colors",
                active
                  ? "border-(--color-ink) bg-(--color-ink) text-(--color-paper)"
                  : "border-(--color-edge) bg-(--color-paper) text-(--color-ink-2) hover:border-(--color-ink-3)",
              )}
            >
              {bucket.label}
            </button>
          );
        })}
      </div>

      {isLoading ? (
        <p className="font-serif text-[13px] italic text-(--color-ink-3)">loading events…</p>
      ) : isError ? (
        <p className="font-mono text-[11px] text-(--color-rule) uppercase tracking-[0.18em]">
          failed to load events
        </p>
      ) : events.length === 0 ? (
        <p className="font-serif text-[14px] italic text-(--color-ink-3)">
          no events yet for this session.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {events.map((evt) => (
            <li key={evt.id}>
              <EventRow event={evt} onExpand={() => setExpandedEvent(evt)} />
            </li>
          ))}
        </ul>
      )}

      <EntityPreviewDrawer
        open={expandedEvent !== null}
        onClose={() => setExpandedEvent(null)}
        title={expandedEvent ? eventTitle(expandedEvent) : ""}
        headerSlot={
          expandedEvent ? (
            <div className="flex flex-wrap items-center gap-2">
              <Stamp tone={kindToTone(expandedEvent.kind)} variant="status">
                {expandedEvent.kind}
              </Stamp>
              <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
                {formatTimestamp(expandedEvent.fired_at)}
              </span>
            </div>
          ) : null
        }
        body={expandedEvent ? <EventDetailBody event={expandedEvent} /> : null}
      />
    </div>
  );
}

function EventRow({ event, onExpand }: { event: ProcessEvent; onExpand: () => void }) {
  const isFireOrFail = event.kind === "tripwire_fire" || event.kind === "validator_fail";
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-(--radius-stamp) border px-3 py-2",
        isFireOrFail
          ? "border-(--color-rule)/40 bg-(--color-rule)/5"
          : "border-(--color-edge) bg-(--color-paper)",
      )}
    >
      <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        {formatTimestamp(event.fired_at)}
      </span>
      <Stamp tone={kindToTone(event.kind)} variant="status">
        {event.kind.replace(/_/g, " ")}
      </Stamp>
      <span className="min-w-0 flex-1 truncate font-sans text-[13px] text-(--color-ink)">
        {eventLabel(event)}
      </span>
      <button
        type="button"
        onClick={onExpand}
        aria-label={`Expand event ${event.id}`}
        className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em] hover:text-(--color-ink)"
      >
        expand →
      </button>
    </div>
  );
}

function EventDetailBody({ event }: { event: ProcessEvent }) {
  // The body renders all fields the typed `ProcessEvent` carries —
  // the events feed is not a fully tagged union (per the comment in
  // `endpoints/events.ts`), so we just dump the optional fields that
  // happen to be present rather than switching on `kind`.
  return (
    <dl className="flex flex-col gap-3 font-mono text-[12px]">
      {event.tripwire_id ? <DetailRow term="tripwire" value={event.tripwire_id} /> : null}
      {event.validator_id ? <DetailRow term="validator" value={event.validator_id} /> : null}
      {event.from_status ? <DetailRow term="from status" value={event.from_status} /> : null}
      {event.to_status ? <DetailRow term="to status" value={event.to_status} /> : null}
      {event.event ? <DetailRow term="event" value={event.event} /> : null}
      {event.artifact ? <DetailRow term="artifact" value={event.artifact} /> : null}
      {event.rejected_by ? <DetailRow term="rejected by" value={event.rejected_by} /> : null}
      {event.feedback_excerpt ? <DetailRow term="feedback" value={event.feedback_excerpt} /> : null}
      {event.evidence ? <DetailRow term="evidence" value={event.evidence} /> : null}
      {event.blocks !== undefined ? <DetailRow term="blocks" value={String(event.blocks)} /> : null}
      {event.resolution ? <DetailRow term="resolution" value={event.resolution.kind} /> : null}
    </dl>
  );
}

function DetailRow({ term, value }: { term: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2">
      <dt className="text-(--color-ink-3) uppercase tracking-[0.06em]">{term}</dt>
      <dd className="text-(--color-ink) whitespace-pre-wrap break-words">{value}</dd>
    </div>
  );
}

function eventLabel(event: ProcessEvent): string {
  // status_transition events carry the from/to pair on the body —
  // surface it directly so the bucket is actionable. Codex P2
  // (2026-04-28).
  if (event.kind === "status_transition" && event.from_status && event.to_status) {
    return `${event.from_status} → ${event.to_status}`;
  }
  if (event.tripwire_id) return event.tripwire_id;
  if (event.validator_id) return event.validator_id;
  if (event.artifact) return event.artifact;
  if (event.event) return event.event;
  // Fallback to the kind itself (with underscores preserved for
  // `getAllByText` matchers in tests) so the row never renders blank.
  return event.kind;
}

function eventTitle(event: ProcessEvent): string {
  return eventLabel(event);
}

function kindToTone(kind: ProcessEventKind): StampTone {
  switch (kind) {
    case "tripwire_fire":
    case "validator_fail":
      return "rule";
    case "validator_pass":
      return "gate";
    case "artifact_rejected":
      return "tripwire";
    case "pm_review_opened":
    case "pm_review_closed":
      return "info";
    default:
      return "default";
  }
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ");
}
