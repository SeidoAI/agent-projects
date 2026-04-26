import { Stamp } from "@/components/ui/stamp";
import { useProject } from "@/lib/api/endpoints/project";
import type { UseProjectWebSocketStatus } from "@/lib/realtime/useProjectWebSocket";
import { useProjectShell } from "./ProjectShell";

/**
 * Top-bar status cluster (env stamp + sync state). Sits to the right
 * of the breadcrumbs in ScreenShell. Keeps the shell file small by
 * extracting the data-fetching parts out of the layout chrome.
 */
export function ProjectStatusCluster({ wsStatus }: { wsStatus: UseProjectWebSocketStatus }) {
  return (
    <div className="flex items-center gap-3 text-[12px]">
      <PhaseStamp />
      <SyncState status={wsStatus} />
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
