import { ArrowDown, GitBranch, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Stream entry types rendered by the Live Monitor turn stream.
 *
 * v1 carries `engagement` boundary markers and `tripwire_fire`
 * markers — the LiveMonitor builds the entry list by interleaving
 * the session's engagement history (when present in v2 runtime) with
 * the per-session process-event stream from KUI-100.
 *
 * Each entry needs a stable `id` (used for React keys and for the
 * `data-testid` hooks the unit tests assert against) and a
 * `timestamp` so the LiveMonitor can sort cross-source events into
 * a single ordered stream.
 */
export type TurnStreamEntry =
  | {
      kind: "engagement";
      id: string;
      timestamp: string;
      trigger: string;
      endedAt: string | null;
      outcome: string | null;
    }
  | {
      kind: "tripwire_fire";
      id: string;
      timestamp: string;
      tripwireId: string;
    };

export interface TurnStreamProps {
  entries: TurnStreamEntry[];
  /** When true, auto-scroll is force-paused regardless of the user's
   *  scroll position. The Live Monitor passes the session's
   *  off-track state (paused / failed / abandoned) so a mid-stream
   *  flip stops chasing the tail and lets the user read what tripped
   *  per the v0.8.x amendment. */
  isOffTrack?: boolean;
  className?: string;
}

/** Threshold (in pixels) below which the stream is considered "at
 *  the bottom" — anything more than this between scrollTop+clientHeight
 *  and scrollHeight surfaces the jump-to-live pill so the user can
 *  catch back up. Matches the Live Monitor amendment's "auto-scroll
 *  pause when the user scrolls up". */
const AT_BOTTOM_THRESHOLD_PX = 40;

export function TurnStream({ entries, isOffTrack = false, className }: TurnStreamProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [userPaused, setUserPaused] = useState(false);
  // The pill (and the auto-scroll-skip) is shown when EITHER the user
  // scrolled up OR the session went off-track. Off-track forces the
  // pause — the user needs to read what happened, not race to the
  // new bottom.
  const paused = userPaused || isOffTrack;

  const handleScroll = useCallback(
    (ev: React.UIEvent<HTMLDivElement>) => {
      // Off-track wins regardless of scroll position. Don't let a
      // bottom-edge scroll event silently re-enable auto-follow.
      if (isOffTrack) {
        setUserPaused(true);
        return;
      }
      const el = ev.currentTarget;
      const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
      setUserPaused(distanceFromBottom > AT_BOTTOM_THRESHOLD_PX);
    },
    [isOffTrack],
  );

  const jumpToLive = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
    setUserPaused(false);
  }, []);

  // Auto-scroll effect — when new entries arrive (or the entry list
  // identity otherwise changes) and the user is not paused, advance
  // scrollTop to scrollHeight so the live tail keeps showing. Without
  // this, jsdom's lack of layout means the test catches what would
  // also break in a real browser when a flexbox column appended new
  // children while the user was at the bottom: the scroll position
  // was left behind and no scroll event fired to even show the pill.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — re-run on entry list growth, not on `paused` flip
  useEffect(() => {
    if (paused) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [entries, paused]);

  // Compute engagement number for each engagement entry — engagements
  // are 1-indexed when they appear in the stream, so a re-engagement
  // shows "engagement #2" etc. per the v0.8.x amendment.
  let engagementOrdinal = 0;

  return (
    <div className={cn("relative flex h-full min-h-0 flex-col", className)}>
      <div
        ref={scrollRef}
        data-testid="turn-stream-scroll"
        data-paused={paused}
        onScroll={handleScroll}
        className="h-full min-h-0 flex-1 overflow-y-auto px-4 py-3"
      >
        {entries.length === 0 ? (
          <div
            data-testid="turn-stream-empty"
            className="flex h-full items-center justify-center font-mono text-[11px] text-(--color-ink-3) uppercase tracking-[0.18em]"
          >
            waiting for the agent's first turn…
          </div>
        ) : (
          <ol className="flex flex-col gap-3">
            {entries.map((entry) => {
              if (entry.kind === "engagement") {
                engagementOrdinal += 1;
                return (
                  <EngagementMarker key={entry.id} ordinal={engagementOrdinal} entry={entry} />
                );
              }
              return <TripwireFire key={entry.id} entry={entry} />;
            })}
          </ol>
        )}
      </div>

      {paused ? (
        <button
          type="button"
          onClick={jumpToLive}
          aria-label="jump to live — resume auto-scroll"
          className="absolute right-4 bottom-4 inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule) px-3 py-1.5 font-mono text-[11px] text-(--color-paper) uppercase tracking-[0.18em] shadow-md transition-opacity hover:opacity-90"
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden strokeWidth={2.4} />
          jump to live
        </button>
      ) : null}
    </div>
  );
}

interface EngagementMarkerProps {
  ordinal: number;
  entry: Extract<TurnStreamEntry, { kind: "engagement" }>;
}

function EngagementMarker({ ordinal, entry }: EngagementMarkerProps) {
  const startedLabel = formatTimestamp(entry.timestamp);
  return (
    <li
      data-testid="engagement-marker"
      className="flex items-center gap-2 border-(--color-edge) border-t pt-3"
    >
      <GitBranch className="h-3.5 w-3.5 text-(--color-ink-2)" aria-hidden strokeWidth={2} />
      <span className="font-mono text-[10px] text-(--color-ink-2) uppercase tracking-[0.18em]">
        engagement #{ordinal}
      </span>
      <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        · {entry.trigger} · {startedLabel}
      </span>
    </li>
  );
}

interface TripwireFireProps {
  entry: Extract<TurnStreamEntry, { kind: "tripwire_fire" }>;
}

function TripwireFire({ entry }: TripwireFireProps) {
  const firedLabel = formatTimestamp(entry.timestamp);
  return (
    <li
      data-testid={`tripwire-fire-${entry.id}`}
      className="flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-rule)/40 bg-(--color-rule)/5 px-3 py-2"
    >
      <Zap className="h-3.5 w-3.5 text-(--color-rule)" aria-hidden strokeWidth={2.2} />
      <span className="font-mono text-[10px] text-(--color-rule) uppercase tracking-[0.18em]">
        agent received tripwire
      </span>
      <span className="font-mono text-[11px] text-(--color-ink) tracking-[0.04em]">
        {entry.tripwireId}
      </span>
      <span className="ml-auto font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        {firedLabel}
      </span>
    </li>
  );
}

/** YYYY-MM-DD HH:MM — used for engagement-boundary dividers and
 *  tripwire-fire timestamps. Falls back to the raw value when the
 *  timestamp can't be parsed (defensive — the backend may emit a
 *  string we can't read on the wire). */
function formatTimestamp(raw: string): string {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toISOString().slice(0, 16).replace("T", " ");
}
