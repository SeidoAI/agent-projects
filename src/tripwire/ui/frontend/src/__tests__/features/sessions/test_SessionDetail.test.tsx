import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { Route } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { SessionDetail } from "@/features/sessions/SessionDetail";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import type { SessionDetail as SessionDetailType } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeRepoBinding, makeSessionDetail } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

const SESSION_DETAIL_EXTRAS = (
  <Route path="/p/:projectId/sessions" element={<div>sessions stub</div>} />
);

function fixtureSession(overrides: Partial<SessionDetailType> = {}): SessionDetailType {
  return makeSessionDetail({
    id: "sess-a",
    name: "Foundation packaging",
    agent: "backend-coder",
    status: "executing",
    issues: ["KUI-1"],
    estimated_size: "M",
    repos: [makeRepoBinding()],
    task_progress: { done: 1, total: 3 },
    plan_md: "# Plan\n\nContent here.",
    grouping_rationale: null,
    engagements: [],
    ...overrides,
  });
}

function setupServer(events: { events: unknown[]; next_cursor: null } = { events: [], next_cursor: null }) {
  server.use(
    http.get("/api/projects/p1/events", () => HttpResponse.json(events)),
    http.get("/api/projects/p1/inbox", () => HttpResponse.json([])),
  );
}

afterEach(() => {
  cleanup();
});

describe("SessionDetail (v0.8 — Option C)", () => {
  it("renders header with status pill, mini-wire, and the plan / engagements / events sections", async () => {
    setupServer();
    const session = fixtureSession();
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.session("p1", session.id), session);

    renderWithProviders(<SessionDetail />, {
      queryClient: qc,
      initialPath: `/p/p1/sessions/${session.id}`,
      routePath: "/p/:projectId/sessions/:sid",
      extraRoutes: SESSION_DETAIL_EXTRAS,
    });

    expect(screen.getByText("Foundation packaging")).toBeInTheDocument();

    // Status pill renders the status string. (Mini-wire is SVG-only;
    // we don't assert its internal markup here — the dashboard's wire
    // tests already cover its rendering.)
    expect(screen.getByText(/executing/i)).toBeInTheDocument();

    // Three body sections — assert by their headings.
    expect(screen.getByRole("heading", { name: /plan/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /engagements/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /events/i })).toBeInTheDocument();
  });

  it("flips the header into alert chrome when the session is off-track (paused)", async () => {
    setupServer();
    const session = fixtureSession({ status: "paused" });
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.session("p1", session.id), session);

    const { container } = renderWithProviders(<SessionDetail />, {
      queryClient: qc,
      initialPath: `/p/p1/sessions/${session.id}`,
      routePath: "/p/:projectId/sessions/:sid",
      extraRoutes: SESSION_DETAIL_EXTRAS,
    });

    const header = container.querySelector("header[data-off-track]");
    expect(header).not.toBeNull();
    expect(header?.getAttribute("data-off-track")).toBe("true");
    // The off-track header carries an AlertTriangle icon next to the
    // session id; it's `aria-hidden`, so we look it up via the wrapping
    // header rather than role.
    expect(header?.querySelector("svg")).not.toBeNull();
  });

  it("surfaces the inbox cross-link chip when an unresolved entry references this session", async () => {
    const inboxItems: InboxItem[] = [
      {
        id: "inb-1",
        bucket: "blocked",
        title: "Needs human review",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-27T12:00:00Z",
        references: [{ session: "sess-a" }],
        escalation_reason: null,
        resolved: false,
        resolved_at: null,
        resolved_by: null,
      },
      {
        // Resolved entries should NOT count toward the chip.
        id: "inb-2",
        bucket: "fyi",
        title: "Earlier ping",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-26T08:00:00Z",
        references: [{ session: "sess-a" }],
        escalation_reason: null,
        resolved: true,
        resolved_at: "2026-04-26T09:00:00Z",
        resolved_by: "user",
      },
      {
        // Different session — should NOT count.
        id: "inb-3",
        bucket: "blocked",
        title: "Other session",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-27T11:00:00Z",
        references: [{ session: "sess-b" }],
        escalation_reason: null,
        resolved: false,
        resolved_at: null,
        resolved_by: null,
      },
    ];
    server.use(
      http.get("/api/projects/p1/events", () =>
        HttpResponse.json({ events: [], next_cursor: null }),
      ),
      http.get("/api/projects/p1/inbox", () => HttpResponse.json(inboxItems)),
    );

    const session = fixtureSession();
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.session("p1", session.id), session);

    renderWithProviders(<SessionDetail />, {
      queryClient: qc,
      initialPath: `/p/p1/sessions/${session.id}`,
      routePath: "/p/:projectId/sessions/:sid",
      extraRoutes: SESSION_DETAIL_EXTRAS,
    });

    // Chip text reflects the count + bucket of the active references.
    const chip = await screen.findByRole("button", { name: /inbox.*1.*blocked/i });
    expect(chip).toBeInTheDocument();

    // Resolved + foreign-session entries should not show.
    expect(screen.queryByText(/Earlier ping/)).not.toBeInTheDocument();

    // Click → drawer opens with the entry's title.
    fireEvent.click(chip);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Needs human review")).toBeInTheDocument();
  });

  it("renders the engagement list when runtime_state.engagements has entries", async () => {
    setupServer();
    const session = fixtureSession({
      engagements: [
        {
          engagement_id: "e1",
          started_at: "2026-04-26T12:00:00Z",
          ended_at: "2026-04-26T13:00:00Z",
          trigger: "spawn",
          outcome: "paused",
        },
      ],
    });
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.session("p1", session.id), session);

    renderWithProviders(<SessionDetail />, {
      queryClient: qc,
      initialPath: `/p/p1/sessions/${session.id}`,
      routePath: "/p/:projectId/sessions/:sid",
      extraRoutes: SESSION_DETAIL_EXTRAS,
    });

    expect(await screen.findByText(/engagement #1/i)).toBeInTheDocument();
  });

  it("renders 'not found' when the session API returns 404", async () => {
    setupServer();
    server.use(
      http.get("/api/projects/p1/sessions/missing", () =>
        HttpResponse.json({ detail: "missing", code: "session/not_found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<SessionDetail />, {
      initialPath: "/p/p1/sessions/missing",
      routePath: "/p/:projectId/sessions/:sid",
      extraRoutes: SESSION_DETAIL_EXTRAS,
    });

    expect(await screen.findByText("Session not found")).toBeInTheDocument();
  });
});
