import { Stamp } from "@/components/ui/stamp";
import { useSessionsList } from "@/features/dashboard/hooks/useProjectStats";
import { useProject } from "@/lib/api/endpoints/project";
import type { UseProjectWebSocketStatus } from "@/lib/realtime/useProjectWebSocket";
import { useProjectShell } from "./ProjectShell";

/**
 * Top-bar status cluster (env stamp + session counts + sync state).
 * Sits to the right of the breadcrumbs in ScreenShell. Keeps the
 * shell file small by extracting the data-fetching parts out of the
 * layout chrome.
 *
 * The session counts (executing + queued) are hidden on narrow
 * viewports via `hidden md:inline-flex` so the bar doesn't crowd
 * when the window is tight.
 */
export function ProjectStatusCluster({ wsStatus }: { wsStatus: UseProjectWebSocketStatus }) {
  return (
    <div className="flex items-center gap-3 text-[12px]">
      <SessionStatusCluster />
      <PhaseStamp />
      <SyncState status={wsStatus} />
    </div>
  );
}

function SessionStatusCluster() {
  const { projectId } = useProjectShell();
  const { data: sessions } = useSessionsList(projectId);
  if (!sessions) return null;
  const counts = sessions.reduce<Record<string, number>>((acc, s) => {
    const k = s.current_state ?? s.status ?? "unknown";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
  // Show the two states the PM cares about most at a glance — what's
  // running and what's about to run. The full breakdown lives in the
  // Issue status grid + the Live now card on the dashboard body.
  const executing = counts.executing ?? 0;
  const queued = counts.queued ?? 0;
  return (
    <div className="hidden items-center gap-2 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em] md:inline-flex">
      <span>
        <span className="text-(--color-rule)">{executing}</span> exec
      </span>
      <span aria-hidden className="text-(--color-edge)">
        ·
      </span>
      <span>
        <span className="text-(--color-ink)">{queued}</span> queued
      </span>
    </div>
  );
}

function PhaseStamp() {
  const { projectId } = useProjectShell();
  const { data } = useProject(projectId);
  if (!data) return null;
  return <Stamp tone="default">phase · {data.phase}</Stamp>;
}

function SyncState({ status }: { status: UseProjectWebSocketStatus }) {
  // Three-state indicator. The dot colour matches whichever mood the
  // socket is in; the label is monospaced so the column stays visually
  // anchored across status changes.
  const tone =
    status === "open"
      ? "var(--color-gate)"
      : status === "connecting"
        ? "var(--color-tripwire)"
        : "var(--color-rule)";
  const label = status === "open" ? "live" : status === "connecting" ? "linking" : "offline";
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-(--color-ink-2) text-[11px]">
      <span className="block h-1.5 w-1.5 rounded-full" style={{ background: tone }} aria-hidden />
      {label}
    </span>
  );
}
