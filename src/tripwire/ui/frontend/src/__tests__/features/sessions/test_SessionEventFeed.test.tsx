import { cleanup, fireEvent, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SessionEventFeed } from "@/features/sessions/SessionEventFeed";
import type { ProcessEvent } from "@/lib/api/endpoints/events";
import { server } from "../../mocks/server";
import { renderWithProviders } from "../../test-utils";

function makeEvent(overrides: Partial<ProcessEvent>): ProcessEvent {
  return {
    id: "evt-1",
    kind: "tripwire_fire",
    fired_at: "2026-04-27T10:00:00Z",
    session_id: "sess-a",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("SessionEventFeed", () => {
  it("renders an empty-state hint when the feed is empty", async () => {
    server.use(
      http.get("/api/projects/p1/events", () =>
        HttpResponse.json({ events: [], next_cursor: null }),
      ),
    );

    renderWithProviders(<SessionEventFeed projectId="p1" sessionId="sess-a" />);
    expect(await screen.findByText(/no events yet for this session/i)).toBeInTheDocument();
  });

  it("renders one row per event with kind stamp + relative-ish timestamp", async () => {
    server.use(
      http.get("/api/projects/p1/events", () =>
        HttpResponse.json({
          events: [
            makeEvent({ id: "e1", kind: "tripwire_fire", tripwire_id: "self-review" }),
            makeEvent({
              id: "e2",
              kind: "validator_pass",
              validator_id: "v_ref_resolution",
              fired_at: "2026-04-27T11:00:00Z",
            }),
            makeEvent({
              id: "e3",
              kind: "status_transition",
              fired_at: "2026-04-27T12:00:00Z",
            }),
          ],
          next_cursor: null,
        }),
      ),
    );

    renderWithProviders(<SessionEventFeed projectId="p1" sessionId="sess-a" />);

    expect(await screen.findByText("self-review")).toBeInTheDocument();
    expect(screen.getByText("v_ref_resolution")).toBeInTheDocument();
    // status_transition row falls back to its kind label
    expect(screen.getAllByText(/status_transition/i).length).toBeGreaterThan(0);
  });

  it("filter chip narrows the visible events to the selected kind bucket", async () => {
    server.use(
      http.get("/api/projects/p1/events", ({ request }) => {
        const kinds = new URL(request.url).searchParams.getAll("kind");
        const all: ProcessEvent[] = [
          makeEvent({ id: "e1", kind: "tripwire_fire", tripwire_id: "self-review" }),
          makeEvent({
            id: "e2",
            kind: "validator_pass",
            validator_id: "v_ref_resolution",
            fired_at: "2026-04-27T11:00:00Z",
          }),
        ];
        const filtered = kinds.length ? all.filter((e) => kinds.includes(e.kind)) : all;
        return HttpResponse.json({ events: filtered, next_cursor: null });
      }),
    );

    renderWithProviders(<SessionEventFeed projectId="p1" sessionId="sess-a" />);
    expect(await screen.findByText("v_ref_resolution")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /firings/i }));

    // After narrowing, validator_pass should disappear; tripwire_fire stays.
    await screen.findByText("self-review");
    expect(screen.queryByText("v_ref_resolution")).not.toBeInTheDocument();
  });

  it("clicking 'expand →' on a row opens the EntityPreviewDrawer for that event", async () => {
    server.use(
      http.get("/api/projects/p1/events", () =>
        HttpResponse.json({
          events: [
            makeEvent({
              id: "e1",
              kind: "validator_fail",
              validator_id: "v_ref_resolution",
              evidence: "[[auth-token]] is stale (last refreshed 18d ago)",
            }),
          ],
          next_cursor: null,
        }),
      ),
    );

    renderWithProviders(<SessionEventFeed projectId="p1" sessionId="sess-a" />);
    fireEvent.click(await screen.findByRole("button", { name: /expand event e1/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/auth-token/)).toBeInTheDocument();
  });
});
