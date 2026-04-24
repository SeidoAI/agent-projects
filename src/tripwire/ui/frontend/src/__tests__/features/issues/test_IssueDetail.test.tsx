import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IssueDetail as IssueDetailView } from "@/features/issues/IssueDetail";
import type { IssueDetail, IssueValidationReport } from "@/lib/api/endpoints/issues";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

async function openDropdown(trigger: HTMLElement) {
  // Radix DropdownMenu triggers open on pointerdown + pointerup, not click.
  // jsdom does not fire pointer events from fireEvent.click, so we fire
  // them explicitly here.
  fireEvent.pointerDown(trigger, { button: 0, pointerType: "mouse" });
  fireEvent.pointerUp(trigger, { button: 0, pointerType: "mouse" });
}

vi.mock("sonner", () => ({
  toast: {
    success: toastMocks.success,
    error: toastMocks.error,
  },
}));

function baseIssue(overrides: Partial<IssueDetail> = {}): IssueDetail {
  return {
    id: "KUI-42",
    title: "Implement auth endpoint",
    status: "in_progress",
    priority: "high",
    executor: "ai",
    verifier: "required",
    kind: null,
    agent: null,
    labels: ["domain/backend"],
    parent: "KUI-8",
    repo: "SeidoAI/tripwire",
    blocked_by: [],
    is_blocked: false,
    is_epic: false,
    body: "See [[user-model]] and [[old-node]] and [[missing]].",
    refs: [
      { ref: "user-model", resolves_as: "node", is_stale: false },
      { ref: "old-node", resolves_as: "node", is_stale: true },
      { ref: "missing", resolves_as: "dangling", is_stale: false },
    ],
    created_at: "2026-04-14T11:30:00",
    updated_at: "2026-04-15T09:00:00",
    ...overrides,
  };
}

function baseProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: "p1",
    name: "Demo",
    key_prefix: "KUI",
    phase: "executing",
    status_transitions: {
      in_progress: ["in_review", "blocked"],
      todo: ["in_progress"],
    },
    dir: "/tmp/demo",
    ...overrides,
  };
}

function prime(
  issue: IssueDetail | undefined,
  project: ProjectDetail | undefined,
): { wrapper: ({ children }: { children: ReactNode }) => ReactElement; qc: QueryClient } {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (issue) {
    qc.setQueryData(queryKeys.issue("p1", issue.id), issue);
  }
  if (project) {
    qc.setQueryData(queryKeys.project("p1"), project);
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/issues/KUI-42"]}>
        <Routes>
          <Route path="/p/:projectId/issues/:key" element={children} />
          <Route path="/p/:projectId/board" element={<div>Board stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper, qc };
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() => new Promise(() => {})),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  toastMocks.success.mockReset();
  toastMocks.error.mockReset();
});

describe("IssueDetail", () => {
  it("renders header, badges, body, refs, and timeline", () => {
    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });

    expect(screen.getByText("KUI-42")).toBeInTheDocument();
    expect(screen.getByText("Implement auth endpoint")).toBeInTheDocument();
    expect(screen.getByText(/Epic:/)).toBeInTheDocument();
    expect(screen.getByText("in_progress")).toBeInTheDocument();
    expect(screen.getByText("priority: high")).toBeInTheDocument();
    expect(screen.getByText("executor: ai")).toBeInTheDocument();
    expect(screen.getByText("domain/backend")).toBeInTheDocument();
    expect(screen.getByText(/repo: SeidoAI\/tripwire/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /References/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Timeline/ })).toBeInTheDocument();
  });

  it("renders each ref type with the correct status icon", () => {
    const { wrapper } = prime(baseIssue(), baseProject());
    const { container } = render(<IssueDetailView />, { wrapper });

    const userModelRow = container.querySelector('li[data-ref-token="user-model"]');
    expect(userModelRow?.querySelector('[data-status="resolved"]')).not.toBeNull();

    const staleRow = container.querySelector('li[data-ref-token="old-node"]');
    expect(staleRow?.querySelector('[data-status="stale"]')).not.toBeNull();
    expect(staleRow?.textContent).toContain("stale");

    const danglingRow = container.querySelector('li[data-ref-token="missing"]');
    expect(danglingRow?.querySelector('[data-status="dangling"]')).not.toBeNull();
    expect(danglingRow?.textContent).toContain("dangling");
  });

  it("renders 'not found' when the API returns 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: "Issue 'KUI-99' not found.", code: "issue/not_found" }),
            { status: 404, headers: { "content-type": "application/json" } },
          ),
        ),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(queryKeys.project("p1"), baseProject());
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/issues/KUI-99"]}>
          <Routes>
            <Route path="/p/:projectId/issues/:key" element={children} />
            <Route path="/p/:projectId/board" element={<div>Board stub</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    render(<IssueDetailView />, { wrapper });

    expect(await screen.findByText("Issue not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to board/ })).toHaveAttribute(
      "href",
      "/p/p1/board",
    );
  });

  it("fires the PATCH mutation when a status transition is chosen", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...baseIssue(), status: "in_review" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });

    await openDropdown(screen.getByRole("button", { name: /Change status/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "in_review" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/p1/issues/KUI-42",
        expect.objectContaining({ method: "PATCH" }),
      );
    });
    expect(toastMocks.success).toHaveBeenCalledWith("Status → in_review");
  });

  it("shows an error toast when the PATCH returns 409 invalid_transition", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Cannot move from in_progress to done.",
          code: "issue/invalid_transition",
        }),
        { status: 409, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const project = baseProject({ status_transitions: { in_progress: ["done"] } });
    const { wrapper } = prime(baseIssue(), project);
    render(<IssueDetailView />, { wrapper });

    await openDropdown(screen.getByRole("button", { name: /Change status/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "done" }));

    await waitFor(() => {
      expect(toastMocks.error).toHaveBeenCalledWith(expect.stringContaining("Cannot move"));
    });
  });

  it("fires validate and shows a success toast when the report has 0 errors", async () => {
    // Backend ValidationReport.to_json() shape: errors/warnings are ARRAYS;
    // numeric counts live under summary.errors / summary.warnings.
    const report: IssueValidationReport = {
      version: 1,
      exit_code: 0,
      summary: { errors: 0, warnings: 0, fixed: 0 },
      categories: {},
      errors: [],
      warnings: [],
      fixed: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(report), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/p1/issues/KUI-42/validate",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(toastMocks.success).toHaveBeenCalledWith("Validation passed.");
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("shows a warning count in the success toast when errors=0 but warnings>0", async () => {
    const report: IssueValidationReport = {
      version: 1,
      exit_code: 1,
      summary: { errors: 0, warnings: 2, fixed: 0 },
      categories: {
        ref: { errors: 0, warnings: 2, fixed: 0 },
      },
      errors: [],
      warnings: [
        { code: "ref/stale", severity: "warning", message: "..." },
        { code: "ref/stale", severity: "warning", message: "..." },
      ],
      fixed: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(report), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() =>
      expect(toastMocks.success).toHaveBeenCalledWith("Validation passed (2 warnings)."),
    );
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("shows an error toast with category summary when errors>0", async () => {
    const report: IssueValidationReport = {
      version: 1,
      exit_code: 2,
      summary: { errors: 2, warnings: 1, fixed: 0 },
      categories: {
        ref: { errors: 1, warnings: 1, fixed: 0 },
        issue_artifact: { errors: 1, warnings: 0, fixed: 0 },
      },
      errors: [
        { code: "ref/dangling", severity: "error", message: "..." },
        { code: "issue_artifact/missing", severity: "error", message: "..." },
      ],
      warnings: [{ code: "ref/stale", severity: "warning", message: "..." }],
      fixed: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(report), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => expect(toastMocks.error).toHaveBeenCalled());
    const msg = toastMocks.error.mock.calls[0]?.[0] as string;
    expect(msg).toContain("2 errors");
    expect(msg).toContain("1 warnings");
    expect(msg).toContain("ref×2");
    expect(msg).toContain("issue_artifact×1");
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it("renders the 'Open in editor' link using the project dir", () => {
    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });

    const link = screen.getByRole("link", { name: /Open issue YAML in editor/ });
    expect(link).toHaveAttribute("href", "file:///tmp/demo/issues/KUI-42/issue.yaml");
  });

  it("disables the 'Change status' button when no transitions exist", () => {
    const project = baseProject();
    project.status_transitions = {};
    const { wrapper } = prime(baseIssue(), project);
    render(<IssueDetailView />, { wrapper });

    const btn = screen.getByRole("button", { name: /Change status/ });
    expect(btn).toBeDisabled();
  });

  it("does not call validate on mount", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime(baseIssue(), baseProject());
    render(<IssueDetailView />, { wrapper });

    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/validate"),
      expect.anything(),
    );
  });
});
