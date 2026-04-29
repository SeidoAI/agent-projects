import type { QueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/api/queryKeys";
import type {
  FileChangedEvent,
  TripwireUiEvent,
  ValidationCompletedEvent,
  ValidationStatusData,
} from "./events";

/**
 * Route a typed WebSocket event to the matching TanStack cache update.
 *
 * `file_changed` invalidates the key that owns the affected entity
 * (e.g. `entity_type: "issue"` → `issues(pid)` + `issue(pid, entity_id)`).
 * `artifact_updated` invalidates the per-session artifact keys.
 * `validation_completed` writes directly into the `validationStatus` key
 * (the backend has no GET endpoint yet — the event is the source of
 * truth for the badge's error count). v2 stubs + heartbeats fall
 * through as no-ops.
 */
export function dispatchEvent(event: TripwireUiEvent, queryClient: QueryClient): void {
  switch (event.type) {
    case "file_changed":
      dispatchFileChanged(event, queryClient);
      return;

    case "artifact_updated":
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifact(event.project_id, event.session_id, event.artifact_name),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.sessionArtifacts(event.project_id, event.session_id),
      });
      return;

    case "validation_completed":
      applyValidationCompleted(event, queryClient);
      return;

    case "process_event":
      // KUI-100 / KUI-107 — a tripwire fire / validator pass-or-fail
      // / status transition / etc. landed in `.tripwire/events/...`.
      // The Live Monitor's `useWorkflowEvents` query hangs off the
      // `events(pid, params)` prefix; invalidating the project-level
      // prefix covers every variant a consumer might have opened
      // (no-filter, session-scoped, kind-filtered) so the right rail
      // and turn stream pick up the new event without a reload.
      queryClient.invalidateQueries({
        queryKey: ["projects", event.project_id, "events"],
      });
      return;

    case "ping":
    case "pong":
      // Heartbeat — connection liveness only.
      return;

    // v2 stubs — acknowledged here so the discriminated union is
    // exhaustively handled. They never fire in v1.
    case "container_status":
    case "message_received":
    case "github_event":
    case "status_update":
    case "pm_review_completed":
    case "approval_pending":
      return;

    default: {
      // Unknown event kinds: log once and keep the socket open.
      // A runtime miss here means the frontend mirror drifted from
      // `tripwire.ui.events` — update `events.ts` + add a case above.
      const unknown: { type?: unknown } = event as { type?: unknown };
      console.warn("[tripwire-ui] unhandled websocket event", unknown.type);
    }
  }
}

function dispatchFileChanged(event: FileChangedEvent, queryClient: QueryClient): void {
  const { project_id: pid, entity_type, entity_id } = event;

  // Workflow graph is built from code registries at request time
  // and isn't tied to any single `EntityType`; bust it on every
  // file_changed so the workflow map picks up new validators /
  // tripwires / artifact definitions without the user reloading.
  // Invalidation is prefix-matched, so both PM-mode and default
  // cache variants flush together.
  queryClient.invalidateQueries({ queryKey: queryKeys.workflow(pid) });

  switch (entity_type) {
    case "issue":
      queryClient.invalidateQueries({ queryKey: queryKeys.issues(pid) });
      queryClient.invalidateQueries({ queryKey: queryKeys.issue(pid, entity_id) });
      // Issue status/dependency edits change the dep graph layout.
      queryClient.invalidateQueries({ queryKey: queryKeys.graph(pid, "deps") });
      return;

    case "node":
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes(pid) });
      queryClient.invalidateQueries({ queryKey: queryKeys.node(pid, entity_id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.graph(pid, "deps") });
      queryClient.invalidateQueries({ queryKey: queryKeys.graph(pid, "concept") });
      return;

    case "session":
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions(pid) });
      queryClient.invalidateQueries({ queryKey: queryKeys.session(pid, entity_id) });
      return;

    case "agent_def":
      // Agent definitions flow through sessions — bust the list so the
      // renderer picks up any renamed/new agents without a manual refresh.
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions(pid) });
      return;

    case "project":
      queryClient.invalidateQueries({ queryKey: queryKeys.project(pid) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projects() });
      return;

    case "enum":
      queryClient.invalidateQueries({ queryKey: queryKeys.enum(pid, entity_id) });
      return;

    case "artifact":
    case "scoping-artifact":
      // The companion `artifact_updated` event carries the session id
      // so the specific key can be targeted; here we broaden to the
      // session-artifacts prefix the router already scopes by project.
      queryClient.invalidateQueries({ queryKey: ["sessions", pid] });
      return;

    case "inbox":
      // PM agent wrote / resolved an inbox entry. Bust both the list
      // (so the dashboard panels pick up the new state) and the
      // single-entry key (so any open preview drawer refreshes).
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox(pid) });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxItem(pid, entity_id) });
      return;

    default: {
      const unknownType: string = entity_type;
      console.warn("[tripwire-ui] unhandled file_changed entity_type", unknownType);
    }
  }
}

function applyValidationCompleted(event: ValidationCompletedEvent, queryClient: QueryClient): void {
  const data: ValidationStatusData = {
    errors: event.errors,
    warnings: event.warnings,
    duration_ms: event.duration_ms,
    last_run_at: event.timestamp,
  };
  queryClient.setQueryData(queryKeys.validationStatus(event.project_id), data);
}
