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
  | "scoping-artifact";

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

// v2 stubs — declared so the dispatch table can accept them without
// validation errors, but handled as no-ops in v1.

export interface ContainerStatusEvent {
  type: "container_status";
  timestamp: string;
  project_id: string;
  session_id: string;
  container_id: string;
  status: "running" | "exited" | "stopped";
  exit_code: number | null;
  cpu_percent: string;
  memory_usage: string;
}

export interface MessageReceivedEvent {
  type: "message_received";
  timestamp: string;
  project_id: string;
  session_id: string;
  message_id: string;
  direction: "agent_to_human" | "human_to_agent";
  msg_type: string;
  priority: string;
  author: string;
  preview: string;
}

export interface GitHubEvent {
  type: "github_event";
  timestamp: string;
  project_id: string;
  event_type: "checks_completed" | "review_submitted" | "pr_merged" | "pr_closed";
  repo: string;
  pr_number: number;
  details: Record<string, unknown>;
}

export interface StatusUpdateEvent {
  type: "status_update";
  timestamp: string;
  project_id: string;
  session_id: string;
  state: string;
  summary: string;
}

export interface PmReviewCompletedEvent {
  type: "pm_review_completed";
  timestamp: string;
  project_id: string;
  repo: string;
  pr_number: number;
  passed: boolean;
  failed_checks: string[];
}

export interface ApprovalPendingEvent {
  type: "approval_pending";
  timestamp: string;
  project_id: string;
  session_id: string;
  artifact_name: string;
  agent: string;
}

export type TripwireUiEvent =
  | FileChangedEvent
  | ArtifactUpdatedEvent
  | ValidationCompletedEvent
  | PingEvent
  | PongEvent
  | ContainerStatusEvent
  | MessageReceivedEvent
  | GitHubEvent
  | StatusUpdateEvent
  | PmReviewCompletedEvent
  | ApprovalPendingEvent;

/** Validation state written into the TanStack cache by the event handler. */
export interface ValidationStatusData {
  errors: number;
  warnings: number;
  duration_ms: number;
  last_run_at: string;
}
