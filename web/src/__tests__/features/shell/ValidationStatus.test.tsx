import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ValidationStatus } from "@/features/shell/ValidationStatus";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ValidationStatusData } from "@/lib/realtime/events";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="current-path">{location.pathname}</div>;
}

function renderWith(data: ValidationStatusData | null): {
  rendered: ReturnType<typeof render>;
  queryClient: QueryClient;
} {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  queryClient.setQueryData(queryKeys.validationStatus("p1"), data);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <MemoryRouter initialEntries={["/p/p1/board"]}>
            <Routes>
              <Route
                path="/p/:projectId/*"
                element={
                  <>
                    {children}
                    <LocationProbe />
                  </>
                }
              />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    );
  }
  const rendered = render(<ValidationStatus />, { wrapper: Wrapper });
  return { rendered, queryClient };
}

describe("ValidationStatus", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the 'never run' state when the cache is empty", () => {
    renderWith(null);
    const button = screen.getByRole("button", { name: /not validated yet/i });
    expect(button).toBeInTheDocument();
    expect(button.querySelector("span.bg-red-500")).toBeNull();
  });

  it("renders the clean state with a check when errors === 0", () => {
    renderWith({
      errors: 0,
      warnings: 0,
      duration_ms: 42,
      last_run_at: "2026-04-21T00:00:00.000Z",
    });
    expect(screen.getByRole("button", { name: /validation clean/i })).toBeInTheDocument();
    // Count is hidden when clean.
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  it("renders the error state with the count when errors > 0", () => {
    renderWith({
      errors: 3,
      warnings: 1,
      duration_ms: 120,
      last_run_at: "2026-04-21T00:00:00.000Z",
    });
    const button = screen.getByRole("button", {
      name: /3 validation errors — open issue board to see/i,
    });
    expect(button).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("uses singular 'error' when errors === 1", () => {
    renderWith({
      errors: 1,
      warnings: 0,
      duration_ms: 20,
      last_run_at: "2026-04-21T00:00:00.000Z",
    });
    expect(
      screen.getByRole("button", { name: /1 validation error — open issue board to see/i }),
    ).toBeInTheDocument();
  });

  it("navigates to the validation panel on click", () => {
    renderWith({
      errors: 0,
      warnings: 0,
      duration_ms: 10,
      last_run_at: "2026-04-21T00:00:00.000Z",
    });

    fireEvent.click(screen.getByRole("button", { name: /validation clean/i }));
    expect(screen.getByTestId("current-path").textContent).toBe("/p/p1/validation");
  });
});
