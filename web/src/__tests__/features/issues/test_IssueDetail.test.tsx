import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { Route } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IssueDetail as IssueDetailView } from "@/features/issues/IssueDetail";
import type { IssueDetail, IssueValidationReport } from "@/lib/api/endpoints/issues";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeIssueDetail, makeProject } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

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

const ISSUE_ID = "KUI-42";

function fixtureIssue(overrides: Partial<IssueDetail> = {}): IssueDetail {
  return makeIssueDetail({
    id: ISSUE_ID,
    title: "Implement auth endpoint",
    status: "in_progress",
    priority: "high",
    labels: ["domain/backend"],
    parent: "KUI-8",
    repo: "SeidoAI/tripwire",
    body: "See [[user-model]] and [[old-node]] and [[missing]].",
    refs: [
      { ref: "user-model", resolves_as: "node", is_stale: false },
      { ref: "old-node", resolves_as: "node", is_stale: true },
      { ref: "missing", resolves_as: "dangling", is_stale: false },
    ],
    created_at: "2026-04-14T11:30:00",
    updated_at: "2026-04-15T09:00:00",
    ...overrides,
  });
}

function fixtureProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return makeProject({
    name: "Demo",
    key_prefix: "KUI",
    status_transitions: {
      in_progress: ["in_review", "blocked"],
      todo: ["in_progress"],
    },
    ...overrides,
  });
}

/** Seed cache with the issue + project, and render via the
 *  helper. The `extraRoutes` stub handles in-tree navigation to
 *  the board (the "Back to board" link from the not-found state). */
function renderIssueDetail(opts: {
  issue?: IssueDetail;
  project?: ProjectDetail;
  initialPath?: string;
}) {
  const qc = makeTestQueryClient();
  if (opts.issue) qc.setQueryData(queryKeys.issue("p1", opts.issue.id), opts.issue);
  if (opts.project) qc.setQueryData(queryKeys.project("p1"), opts.project);
  return renderWithProviders(<IssueDetailView />, {
    queryClient: qc,
    initialPath: opts.initialPath ?? `/p/p1/issues/${ISSUE_ID}`,
    routePath: "/p/:projectId/issues/:key",
    extraRoutes: <Route path="/p/:projectId/board" element={<div>Board stub</div>} />,
  });
}

afterEach(() => {
  cleanup();
  toastMocks.success.mockReset();
  toastMocks.error.mockReset();
});

describe("IssueDetail", () => {
  it("renders header, badges, body, refs, and timeline", () => {
    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });

    expect(screen.getByText(ISSUE_ID)).toBeInTheDocument();
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
    const { container } = renderIssueDetail({
      issue: fixtureIssue(),
      project: fixtureProject(),
    });

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
    server.use(
      http.get("/api/projects/p1/issues/KUI-99", () =>
        HttpResponse.json(
          { detail: "Issue 'KUI-99' not found.", code: "issue/not_found" },
          { status: 404 },
        ),
      ),
    );
    renderIssueDetail({ project: fixtureProject(), initialPath: "/p/p1/issues/KUI-99" });

    expect(await screen.findByText("Issue not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to board/ })).toHaveAttribute(
      "href",
      "/p/p1/board",
    );
  });

  it("fires the PATCH mutation when a status transition is chosen", async () => {
    const patchSpy = vi.fn();
    server.use(
      http.patch(`/api/projects/p1/issues/${ISSUE_ID}`, async ({ request }) => {
        patchSpy(request.url, request.method);
        return HttpResponse.json(fixtureIssue({ status: "in_review" }));
      }),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });

    await openDropdown(screen.getByRole("button", { name: /Change status/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "in_review" }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    expect(patchSpy.mock.calls[0]).toEqual([
      expect.stringContaining(`/api/projects/p1/issues/${ISSUE_ID}`),
      "PATCH",
    ]);
    expect(toastMocks.success).toHaveBeenCalledWith("Status → in_review");
  });

  it("shows an error toast when the PATCH returns 409 invalid_transition", async () => {
    server.use(
      http.patch(`/api/projects/p1/issues/${ISSUE_ID}`, () =>
        HttpResponse.json(
          {
            detail: "Cannot move from in_progress to done.",
            code: "issue/invalid_transition",
          },
          { status: 409 },
        ),
      ),
    );

    renderIssueDetail({
      issue: fixtureIssue(),
      project: fixtureProject({ status_transitions: { in_progress: ["done"] } }),
    });

    await openDropdown(screen.getByRole("button", { name: /Change status/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "done" }));

    await waitFor(() =>
      expect(toastMocks.error).toHaveBeenCalledWith(expect.stringContaining("Cannot move")),
    );
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
    const validateSpy = vi.fn();
    server.use(
      http.post(`/api/projects/p1/issues/${ISSUE_ID}/validate`, ({ request }) => {
        validateSpy(request.url, request.method);
        return HttpResponse.json(report);
      }),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });

    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => expect(validateSpy).toHaveBeenCalled());
    expect(validateSpy.mock.calls[0]).toEqual([
      expect.stringContaining(`/api/projects/p1/issues/${ISSUE_ID}/validate`),
      "POST",
    ]);
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
    server.use(
      http.post(`/api/projects/p1/issues/${ISSUE_ID}/validate`, () => HttpResponse.json(report)),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });
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
    server.use(
      http.post(`/api/projects/p1/issues/${ISSUE_ID}/validate`, () => HttpResponse.json(report)),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });
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
    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });

    const link = screen.getByRole("link", { name: /Open issue YAML in editor/ });
    expect(link).toHaveAttribute("href", `file:///tmp/demo/issues/${ISSUE_ID}/issue.yaml`);
  });

  it("disables the 'Change status' button when no transitions exist", () => {
    renderIssueDetail({
      issue: fixtureIssue(),
      project: fixtureProject({ status_transitions: {} }),
    });

    expect(screen.getByRole("button", { name: /Change status/ })).toBeDisabled();
  });

  it("shows the ApiError message in the error toast when validate returns 500", async () => {
    server.use(
      http.post(`/api/projects/p1/issues/${ISSUE_ID}/validate`, () =>
        HttpResponse.json(
          { detail: "Validator crashed.", code: "validate/internal" },
          { status: 500 },
        ),
      ),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });
    fireEvent.click(screen.getByRole("button", { name: /Validate/ }));

    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledWith("Validator crashed."));
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it("does not call validate on mount", () => {
    const validateSpy = vi.fn();
    server.use(
      http.post(`/api/projects/p1/issues/${ISSUE_ID}/validate`, () => {
        validateSpy();
        return HttpResponse.json({});
      }),
    );

    renderIssueDetail({ issue: fixtureIssue(), project: fixtureProject() });

    expect(validateSpy).not.toHaveBeenCalled();
  });
});
