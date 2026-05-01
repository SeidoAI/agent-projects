import { useQuery } from "@tanstack/react-query";
import { cleanup, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeProject } from "./mocks/fixtures";
import { server } from "./mocks/server";
import { makeTestQueryClient, renderWithProviders } from "./test-utils";

function ProjectProbe({ pid }: { pid: string }) {
  const q = useQuery({
    queryKey: queryKeys.project(pid),
    queryFn: () => apiGet<{ id: string; name: string }>(`/api/projects/${pid}`),
  });
  if (q.isLoading) return <span>loading</span>;
  if (q.isError) return <span>error: {String(q.error)}</span>;
  return <span data-testid="probe-name">{q.data?.name}</span>;
}

describe("renderWithProviders + MSW", () => {
  afterEach(() => {
    cleanup();
  });

  it("default handler resolves the project query", async () => {
    renderWithProviders(<ProjectProbe pid="p1" />);
    await waitFor(() =>
      expect(screen.getByTestId("probe-name").textContent).toBe(makeProject().name),
    );
  });

  it("server.use(...) override is honoured for a single test", async () => {
    server.use(
      http.get("/api/projects/p1", () => HttpResponse.json({ id: "p1", name: "Overridden" })),
    );
    renderWithProviders(<ProjectProbe pid="p1" />);
    await waitFor(() => expect(screen.getByTestId("probe-name").textContent).toBe("Overridden"));
  });

  it("returns the queryClient handle so tests can prime the cache", async () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.project("p1"), { id: "p1", name: "Pre-seeded" });
    const { queryClient } = renderWithProviders(<ProjectProbe pid="p1" />, { queryClient: qc });
    expect(queryClient).toBe(qc);
    expect(screen.getByTestId("probe-name").textContent).toBe("Pre-seeded");
  });

  it("an unhandled request fails the suite (smoke)", async () => {
    // Verify MSW is configured with onUnhandledRequest: "error" by
    // making a request to a path no handler covers and confirming
    // the rejection. We swallow console output that MSW emits for
    // unhandled requests so the strict console spy doesn't trip.
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      await expect(apiGet("/api/this-route-does-not-exist")).rejects.toThrow();
    } finally {
      errSpy.mockRestore();
      warnSpy.mockRestore();
    }
  });
});
