import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queryKeys } from "@/lib/api/queryKeys";
import { dispatchEvent } from "@/lib/realtime/eventHandlers";
import type {
  ArtifactUpdatedEvent,
  FileChangedEvent,
  ProcessEventBroadcast,
  ValidationCompletedEvent,
} from "@/lib/realtime/events";

function makeEvent<T extends { type: string }>(event: T): T & { timestamp: string } {
  return { timestamp: "2026-04-21T00:00:00.000Z", ...event };
}

describe("dispatchEvent", () => {
  let queryClient: QueryClient;
  let invalidate: ReturnType<typeof vi.fn>;
  let setQueryData: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    queryClient = new QueryClient();
    invalidate = vi.fn();
    setQueryData = vi.fn();
    queryClient.invalidateQueries = invalidate as unknown as QueryClient["invalidateQueries"];
    queryClient.setQueryData = setQueryData as unknown as QueryClient["setQueryData"];
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function invalidatedKeys(): unknown[][] {
    return invalidate.mock.calls.map((call) => call[0]?.queryKey);
  }

  it("file_changed entity=issue → invalidates issues list, the issue, and the deps graph", () => {
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "issue",
      entity_id: "KUI-42",
      action: "modified",
      path: "issues/KUI-42/issue.yaml",
    });
    dispatchEvent(event, queryClient);

    const keys = invalidatedKeys();
    expect(keys).toContainEqual(queryKeys.issues("p1"));
    expect(keys).toContainEqual(queryKeys.issue("p1", "KUI-42"));
    expect(keys).toContainEqual(queryKeys.graph("p1", "deps"));
  });

  it("file_changed → also busts the workflow key (registry rebuilt at request time)", () => {
    // The workflow graph is computed from code-side registries on
    // every request. None of the existing `EntityType` values
    // cleanly maps to "registry change," so we bust workflow on
    // every `file_changed`. AC#3 (auto-update on new entity)
    // depends on this — without it the WS path is silent.
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "node",
      entity_id: "api-client",
      action: "modified",
      path: "nodes/api-client.yaml",
    });
    dispatchEvent(event, queryClient);
    expect(invalidatedKeys()).toContainEqual(queryKeys.workflow("p1"));
  });

  it("file_changed entity=node → invalidates node lists and graph views", () => {
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "node",
      entity_id: "api-client",
      action: "modified",
      path: "nodes/api-client.yaml",
    });
    dispatchEvent(event, queryClient);

    const keys = invalidatedKeys();
    expect(keys).toContainEqual(queryKeys.nodes("p1"));
    expect(keys).toContainEqual(queryKeys.node("p1", "api-client"));
    expect(keys).toContainEqual(queryKeys.graph("p1", "deps"));
    expect(keys).toContainEqual(queryKeys.graph("p1", "concept"));
  });

  it("file_changed entity=session → invalidates sessions list and the session", () => {
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "session",
      entity_id: "sess-01",
      action: "modified",
      path: "sessions/sess-01/session.yaml",
    });
    dispatchEvent(event, queryClient);

    const keys = invalidatedKeys();
    expect(keys).toContainEqual(queryKeys.sessions("p1"));
    expect(keys).toContainEqual(queryKeys.session("p1", "sess-01"));
  });

  it("file_changed entity=project → invalidates project detail and project list", () => {
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "project",
      entity_id: "config",
      action: "modified",
      path: "project.yaml",
    });
    dispatchEvent(event, queryClient);

    const keys = invalidatedKeys();
    expect(keys).toContainEqual(queryKeys.project("p1"));
    expect(keys).toContainEqual(queryKeys.projects());
  });

  it("file_changed entity=enum → invalidates the named enum", () => {
    const event: FileChangedEvent = makeEvent({
      type: "file_changed",
      project_id: "p1",
      entity_type: "enum",
      entity_id: "agent_state",
      action: "modified",
      path: "enums/agent_state.yaml",
    });
    dispatchEvent(event, queryClient);

    expect(invalidatedKeys()).toContainEqual(queryKeys.enum("p1", "agent_state"));
  });

  it("artifact_updated → invalidates the artifact + session artifacts", () => {
    const event: ArtifactUpdatedEvent = makeEvent({
      type: "artifact_updated",
      project_id: "p1",
      session_id: "sess-01",
      artifact_name: "plan",
      file: "plan.md",
    });
    dispatchEvent(event, queryClient);

    const keys = invalidatedKeys();
    expect(keys).toContainEqual(queryKeys.artifact("p1", "sess-01", "plan"));
    expect(keys).toContainEqual(queryKeys.sessionArtifacts("p1", "sess-01"));
  });

  it("validation_completed → writes the payload into the validationStatus cache", () => {
    const event: ValidationCompletedEvent = makeEvent({
      type: "validation_completed",
      project_id: "p1",
      errors: 2,
      warnings: 1,
      duration_ms: 137,
    });
    dispatchEvent(event, queryClient);

    expect(setQueryData).toHaveBeenCalledWith(queryKeys.validationStatus("p1"), {
      errors: 2,
      warnings: 1,
      duration_ms: 137,
      last_run_at: event.timestamp,
    });
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("process_event → invalidates the workflow events query so the Live Monitor refreshes", () => {
    const event: ProcessEventBroadcast = makeEvent({
      type: "process_event",
      project_id: "p1",
      event_id: "ev-1",
      kind: "jit_prompt_fire",
      session_id: "sess-01",
      fired_at: "2026-04-28T10:00:00Z",
    });
    dispatchEvent(event, queryClient);

    // The frontend's `useWorkflowEvents` keys queries under the
    // `events(pid, params)` prefix; invalidating the project-prefix
    // covers every variant a consumer might have opened (no-filter,
    // session-scoped, kind-filtered).
    const keys = invalidatedKeys();
    expect(keys).toContainEqual(["projects", "p1", "events"]);
  });

  it("ping / pong are no-ops", () => {
    dispatchEvent(makeEvent({ type: "ping" }), queryClient);
    dispatchEvent(makeEvent({ type: "pong" }), queryClient);
    expect(invalidate).not.toHaveBeenCalled();
    expect(setQueryData).not.toHaveBeenCalled();
  });

  it("unknown event kind is logged without throwing", () => {
    const warn = vi.spyOn(console, "warn");
    dispatchEvent(
      { type: "not-a-real-event", timestamp: "t" } as unknown as Parameters<
        typeof dispatchEvent
      >[0],
      queryClient,
    );
    expect(warn).toHaveBeenCalled();
  });
});
