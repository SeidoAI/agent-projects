// Frontend mirror of `tripwire.ui.events` — the discriminated union
// the backend broadcasts over the WebSocket. Keep this file in sync
// with `src/tripwire/ui/events.py`; a divergence means a handler
// branch in `eventHandlers.ts` will fall through to the warn-and-keep-
// open default rather than invalidating a cache.

export type EntityType =
  | "issue"
  | "node"
  | "session"
  | "agent_def"
  | "project"
  | "enum"
  | "artifact"
  | "scoping-artifact"
  | "inbox";

export type FileAction = "created" | "modified" | "deleted";

export interface FileChangedEvent {
  type: "file_changed";
  timestamp: string;
  project_id: string;
  entity_type: EntityType;
  entity_id: string;
  action: FileAction;
  path: string;
}

export interface ArtifactUpdatedEvent {
  type: "artifact_updated";
  timestamp: string;
  project_id: string;
  session_id: string;
  artifact_name: string;
  file: string;
}

export interface ValidationCompletedEvent {
  type: "validation_completed";
  timestamp: string;
  project_id: string;
  errors: number;
  warnings: number;
  duration_ms: number;
}

export interface PingEvent {
  type: "ping";
  timestamp: string;
}

export interface PongEvent {
  type: "pong";
  timestamp: string;
}

/** Mirrors `ProcessEvent` from `tripwire.ui.events` (KUI-100).
 *  A `.tripwire/events/<kind>/<sid>/<n>.json` write classified by
 *  the file watcher; the WS notification is a thin pointer. The Live
 *  Monitor (KUI-107) consumes it to invalidate `useWorkflowEvents`
 *  so tripwire fires + status transitions appear in real time.
 *
 *  Named `ProcessEventBroadcast` rather than `ProcessEvent` to avoid
 *  colliding with the same-named REST type in `endpoints/events.ts`. */
export type ProcessEventKindBroadcast =
  | "jit_prompt_fire"
  | "validator_pass"
  | "validator_fail"
  | "artifact_rejected"
  | "pm_review_opened"
  | "pm_review_closed"
  | "status_transition";

export interface ProcessEventBroadcast {
  type: "process_event";
  timestamp: string;
  project_id: string;
  event_id: string;
  kind: ProcessEventKindBroadcast;
  session_id: string;
  fired_at: string;
}

export type TripwireUiEvent =
  | FileChangedEvent
  | ArtifactUpdatedEvent
  | ValidationCompletedEvent
  | ProcessEventBroadcast
  | PingEvent
  | PongEvent;

/** Validation state written into the TanStack cache by the event handler. */
export interface ValidationStatusData {
  errors: number;
  warnings: number;
  duration_ms: number;
  last_run_at: string;
}
