import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterveneButton } from "@/features/live/InterveneButton";
import { renderWithProviders } from "../../test-utils";
import { server } from "../../mocks/server";

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

describe("InterveneButton — KUI-107 INTERVENE", () => {
  it("calls POST /api/projects/{pid}/sessions/{sid}/pause when clicked", async () => {
    const spy = vi.fn();
    server.use(
      http.post("/api/projects/p1/sessions/v08-foo/pause", ({ request }) => {
        spy(request.url, request.method);
        return HttpResponse.json({
          session_id: "v08-foo",
          status: "paused",
          changed_at: "2026-04-28T12:00:00Z",
        });
      }),
    );

    renderWithProviders(
      <InterveneButton projectId="p1" sessionId="v08-foo" status="executing" />,
    );

    fireEvent.click(screen.getByRole("button", { name: /intervene/i }));

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][1]).toBe("POST");
  });

  it("is disabled when the session is not executing (already paused / done / etc.)", () => {
    renderWithProviders(
      <InterveneButton projectId="p1" sessionId="v08-foo" status="paused" />,
    );

    expect(screen.getByRole("button", { name: /intervene/i })).toBeDisabled();
  });

  it("shows a transient pending state while the mutation is in flight", async () => {
    let release: (() => void) | undefined;
    server.use(
      http.post("/api/projects/p1/sessions/v08-foo/pause", async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({
          session_id: "v08-foo",
          status: "paused",
          changed_at: "2026-04-28T12:00:00Z",
        });
      }),
    );

    renderWithProviders(
      <InterveneButton projectId="p1" sessionId="v08-foo" status="executing" />,
    );

    fireEvent.click(screen.getByRole("button", { name: /intervene/i }));

    // While in flight: button shows "pausing…" copy and is disabled.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /pausing/i })).toBeDisabled(),
    );

    // Release the response so the test can finish without leaking
    // the pending fetch into other tests.
    release?.();
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
  });
});
