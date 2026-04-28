import { cleanup, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { sessionStageColor } from "@/components/ui/session-stage-row";
import { LiveMonitor } from "@/features/live/LiveMonitor";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeSessionDetail } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

const ROUTE = "/p/p1/sessions/v08-foo/live";
const ROUTE_PATTERN = "/p/:projectId/sessions/:sid/live";

describe("LiveMonitor — KUI-107", () => {
  it("renders the LIVE badge with the executing stage colour from sessionStageColor()", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({ id: "v08-foo", status: "executing" }),
    );

    renderWithProviders(<LiveMonitor />, {
      queryClient: qc,
      initialPath: ROUTE,
      routePath: ROUTE_PATTERN,
    });

    const badge = screen.getByTestId("live-badge");
    expect(badge).toHaveTextContent(/^LIVE$/i);
    // Per the v0.8.x amendment the colour is sourced from the
    // canonical stage-colour helper so a future palette change
    // ripples to every surface (dashboard, board, live monitor)
    // without per-surface edits.
    const expectedColour = sessionStageColor("executing");
    expect(badge.style.color).toBe(hexToRgb(expectedColour));
  });

  it("flips header into alert chrome when status is off-track (paused / failed / abandoned)", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({ id: "v08-foo", status: "paused" }),
    );

    renderWithProviders(<LiveMonitor />, {
      queryClient: qc,
      initialPath: ROUTE,
      routePath: ROUTE_PATTERN,
    });

    // No more LIVE badge — replaced by OFF-TRACK chrome.
    expect(screen.queryByTestId("live-badge")).toBeNull();
    expect(screen.getByTestId("off-track-banner")).toHaveTextContent(/off-track/i);
    expect(screen.getByTestId("off-track-banner")).toHaveTextContent(/paused/i);
  });

  it("renders TurnStream + LiveRail beneath the header", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({ id: "v08-foo", status: "executing" }),
    );

    renderWithProviders(<LiveMonitor />, {
      queryClient: qc,
      initialPath: ROUTE,
      routePath: ROUTE_PATTERN,
    });

    expect(screen.getByTestId("turn-stream-scroll")).toBeInTheDocument();
    // Cost ticker lives on the rail; its presence signals LiveRail mounted.
    expect(screen.getByTestId("cost-ticker")).toBeInTheDocument();
  });

  it("shows a not-found state when the session 404s", async () => {
    server.use(
      http.get("/api/projects/p1/sessions/missing", () =>
        HttpResponse.json(
          { detail: "missing not found", code: "session/not_found", extras: {} },
          { status: 404 },
        ),
      ),
    );

    renderWithProviders(<LiveMonitor />, {
      initialPath: "/p/p1/sessions/missing/live",
      routePath: ROUTE_PATTERN,
    });

    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });
});

/** jsdom serialises inline `style.color` to its rgb() form, so assertions
 *  against a stage-row hex need to convert. The helper mirrors what
 *  jsdom does for 6-character hex values. */
function hexToRgb(hex: string): string {
  const captured = /^#?([0-9a-f]{6})$/i.exec(hex)?.[1];
  if (!captured) return hex;
  const num = Number.parseInt(captured, 16);
  const r = (num >> 16) & 0xff;
  const g = (num >> 8) & 0xff;
  const b = num & 0xff;
  return `rgb(${r}, ${g}, ${b})`;
}
