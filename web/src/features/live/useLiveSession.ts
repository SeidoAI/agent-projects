import { useMemo } from "react";

import { sessionStageId } from "@/components/ui/session-stage-row";
import type { ProcessEvent } from "@/lib/api/endpoints/events";
import { useWorkflowEvents } from "@/lib/api/endpoints/events";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { useInbox } from "@/lib/api/endpoints/inbox";
import type { SessionDetail } from "@/lib/api/endpoints/sessions";
import { useSession } from "@/lib/api/endpoints/sessions";

/**
 * Composition hook for the Live Monitor screen (S7).
 *
 * Aggregates the three independent data flows the page needs:
 * - the session detail (for status, cost ticker, current_state)
 * - the per-session process-event stream (JIT prompt fires, status
 *   transitions used as engagement-boundary markers)
 * - the open `cost-approval` inbox entry (when one exists for this
 *   session — the PM agent's "system" version of INTERVENE)
 *
 * The project-scoped `useProjectWebSocket` already lives at
 * ``ProjectShell``, and ``eventHandlers.dispatchEvent`` invalidates
 * the session / inbox / events caches on file_changed messages —
 * so the page reacts in real time without a second subscription
 * here.
 *
 * `isOffTrack` is computed via the canonical 7-stage mapping:
 * `paused`, `failed`, `abandoned` collapse to `off_track`. The
 * Live Monitor watches this flag to flip into alert chrome
 * mid-stream per the v0.8.x amendment.
 */
export interface UseLiveSessionResult {
  session: SessionDetail | undefined;
  isLoading: boolean;
  error: unknown;
  isOffTrack: boolean;
  /** Process events of kind `jit_prompt_fire` scoped to this session,
   *  newest first. Empty when KUI-99 / KUI-100 haven't shipped. */
  jitPromptFires: ProcessEvent[];
  /** Process events of kind `status_transition` scoped to this
   *  session, oldest first. Used to render engagement-boundary
   *  dividers in the turn stream. */
  statusTransitions: ProcessEvent[];
  /** The single open `cost-approval` inbox entry for this session,
   *  if one exists. `null` otherwise — the chip in the right rail
   *  hides itself in that case. */
  costApprovalEntry: InboxItem | null;
}

export function useLiveSession(projectId: string, sessionId: string): UseLiveSessionResult {
  const sessionQuery = useSession(projectId, sessionId);
  const eventsQuery = useWorkflowEvents(projectId, { session_id: sessionId });
  // Filter the inbox to OPEN BLOCKED entries only — the cost-approval
  // chip only matters while the gate is up. Resolved entries shouldn't
  // surface in the right rail.
  const inboxQuery = useInbox(projectId, { bucket: "blocked", resolved: false });

  const session = sessionQuery.data;

  const isOffTrack = useMemo(() => {
    if (!session) return false;
    return sessionStageId(session.status) === "off_track";
  }, [session]);

  const jitPromptFires = useMemo(() => {
    const all = eventsQuery.data?.events ?? [];
    return all
      .filter((e) => e.kind === "jit_prompt_fire" && e.session_id === sessionId)
      .sort((a, b) => new Date(b.fired_at).getTime() - new Date(a.fired_at).getTime());
  }, [eventsQuery.data, sessionId]);

  const statusTransitions = useMemo(() => {
    const all = eventsQuery.data?.events ?? [];
    return all
      .filter((e) => e.kind === "status_transition" && e.session_id === sessionId)
      .sort((a, b) => new Date(a.fired_at).getTime() - new Date(b.fired_at).getTime());
  }, [eventsQuery.data, sessionId]);

  const costApprovalEntry = useMemo<InboxItem | null>(() => {
    const entries = inboxQuery.data ?? [];
    const matched = entries.find(
      (entry) =>
        entry.escalation_reason === "cost-approval" &&
        entry.references.some((ref) => "session" in ref && ref.session === sessionId),
    );
    return matched ?? null;
  }, [inboxQuery.data, sessionId]);

  return {
    session,
    isLoading: sessionQuery.isLoading,
    error: sessionQuery.error,
    isOffTrack,
    jitPromptFires,
    statusTransitions,
    costApprovalEntry,
  };
}
