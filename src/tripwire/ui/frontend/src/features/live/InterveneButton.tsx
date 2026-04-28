import { Hand } from "lucide-react";
import { usePauseSession } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";

/**
 * The human's escape hatch on the Live Monitor (S7) — calls
 * `POST /api/projects/{pid}/sessions/{sid}/pause`, which is the HTTP
 * face on the existing `tripwire session pause` CLI logic.
 *
 * Only enabled while the session is `executing`. Per the plan's
 * INTERVENE amendment this is the human override; the system's
 * gentler version is the cost-approval inbox cross-link in the
 * right rail (which routes through the PM agent).
 */
export interface InterveneButtonProps {
  projectId: string;
  sessionId: string;
  /** Current session status — gates the button. The Live Monitor
   *  passes `session.status` directly so the button reacts as the
   *  WS-driven invalidation refreshes the cache. */
  status: string;
  className?: string;
}

export function InterveneButton({ projectId, sessionId, status, className }: InterveneButtonProps) {
  const pause = usePauseSession(projectId, sessionId);
  const canPause = status === "executing" && !pause.isPending;
  const label = pause.isPending ? "pausing…" : "intervene";
  const ariaLabel = pause.isPending
    ? "pausing the session"
    : "intervene — pause the running session";

  return (
    <button
      type="button"
      onClick={() => pause.mutate()}
      disabled={!canPause}
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-(--radius-stamp) border px-3 py-1.5",
        "font-mono text-[11px] uppercase tracking-[0.18em] transition-colors",
        canPause
          ? "border-(--color-rule) bg-(--color-rule) text-(--color-paper) hover:opacity-90"
          : "cursor-not-allowed border-(--color-edge) bg-(--color-paper-2) text-(--color-ink-3)",
        className,
      )}
    >
      <Hand className="h-3.5 w-3.5" aria-hidden strokeWidth={2.2} />
      {label}
    </button>
  );
}
