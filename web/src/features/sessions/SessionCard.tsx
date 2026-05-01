import { Link } from "react-router-dom";

import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { statusStyle } from "./sessionStatus";
import { TaskProgressBar } from "./TaskProgressBar";

interface SessionCardProps {
  session: SessionSummary;
  projectId: string;
  isFocused?: boolean;
}

/**
 * One session per card. The card is colour-coded by status using the
 * same palette as the flow chips: live work (executing/active) gets a
 * saturated coloured header band, lower-priority statuses get a subtler
 * tint so the eye lands on what's running first.
 */
export function SessionCard({ session, projectId, isFocused }: SessionCardProps) {
  const style = statusStyle(session.status);
  const color = style.color;
  // Treat order 0 (live) as "loud": full coloured header band + white title.
  // Everything else gets the muted left-stripe + tinted status pill.
  const isLive = style.order === 0;

  return (
    <Link
      to={`/p/${projectId}/sessions/${session.id}`}
      className="relative block overflow-hidden rounded-md border bg-background shadow-sm transition-colors hover:border-foreground/30"
      data-session-id={session.id}
      data-focused={isFocused ? "true" : undefined}
      style={{
        borderColor: isFocused ? color : undefined,
        boxShadow: isFocused ? `0 0 0 1px ${color}` : undefined,
      }}
    >
      {/* Header band — colour-coded by status. */}
      <div
        className="flex items-start justify-between gap-2 px-4 py-3"
        style={{
          backgroundColor: isLive ? color : "transparent",
          color: isLive ? "var(--color-paper)" : undefined,
        }}
      >
        {!isLive && (
          <span
            aria-hidden
            className="absolute top-0 bottom-0 left-0 w-1.5"
            style={{ backgroundColor: color }}
          />
        )}
        <div className={isLive ? "" : "pl-2"}>
          <h3
            className="font-semibold leading-tight"
            style={isLive ? { color: "var(--color-paper)" } : undefined}
          >
            {session.name}
          </h3>
          <p
            className="text-xs"
            style={{
              color: isLive
                ? "color-mix(in srgb, var(--color-paper) 80%, transparent)"
                : "var(--color-ink-3)",
            }}
          >
            {session.id} · {session.agent}
          </p>
        </div>
        <span
          data-badge="status"
          className="shrink-0 whitespace-nowrap rounded-(--radius-stamp) border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em]"
          style={{
            color: isLive ? "var(--color-paper)" : color,
            borderColor: isLive ? "var(--color-paper)" : color,
            backgroundColor: isLive
              ? "color-mix(in srgb, var(--color-paper) 15%, transparent)"
              : "transparent",
          }}
        >
          {style.label}
        </span>
      </div>

      <div className="px-4 pb-4 pl-6">
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{session.issues.length} issues</span>
          {session.estimated_size ? <span>· size: {session.estimated_size}</span> : null}
        </div>

        {session.blocked_by_sessions.length > 0 ? (
          <p className="mt-1 text-xs text-amber-500" data-field="blocked-by">
            blocked by: {session.blocked_by_sessions.join(", ")}
          </p>
        ) : null}

        <div className="mt-3">
          <TaskProgressBar progress={session.task_progress} />
        </div>
      </div>
    </Link>
  );
}
