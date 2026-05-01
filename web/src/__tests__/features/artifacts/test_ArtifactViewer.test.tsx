import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ArtifactList } from "@/features/artifacts/ArtifactList";
import { ArtifactViewer } from "@/features/artifacts/ArtifactViewer";
import { parseChecklist } from "@/features/artifacts/TaskChecklistRender";
import type {
  ArtifactContent,
  ArtifactManifest,
  ArtifactStatus,
} from "@/lib/api/endpoints/artifacts";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeArtifactSpec, makeArtifactStatus } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: toastMocks.success, error: toastMocks.error },
}));

const SPECS = {
  plan: makeArtifactSpec({ name: "plan", approval_gate: true }),
  "task-checklist": makeArtifactSpec({
    name: "task-checklist",
    file: "task-checklist.md",
    template: "task-checklist",
    produced_at: "executing",
    produced_by: "executor",
  }),
  handoff: makeArtifactSpec({
    name: "handoff",
    file: "handoff.yaml",
    template: "handoff",
    produced_at: "reviewing",
    produced_by: "agent",
    required: false,
  }),
  "extra-1": makeArtifactSpec({
    name: "extra-1",
    file: "extra-1.md",
    template: "plain",
    produced_at: "executing",
    produced_by: "agent",
    required: false,
  }),
  "extra-2": makeArtifactSpec({
    name: "extra-2",
    file: "extra-2.md",
    template: "plain",
    produced_at: "executing",
    produced_by: "agent",
    required: false,
  }),
};

function fixtureManifest(): ArtifactManifest {
  return {
    artifacts: [
      SPECS.plan,
      SPECS["task-checklist"],
      SPECS.handoff,
      SPECS["extra-1"],
      SPECS["extra-2"],
    ],
  };
}

function statusFor(name: keyof typeof SPECS, present: boolean): ArtifactStatus {
  return makeArtifactStatus(SPECS[name], present);
}

function renderWithCache(
  ui: React.ReactElement,
  opts: {
    manifest: ArtifactManifest;
    statuses: ArtifactStatus[];
    content?: Record<string, ArtifactContent>;
  },
) {
  const qc = makeTestQueryClient();
  qc.setQueryData(queryKeys.artifactManifest("p1"), opts.manifest);
  qc.setQueryData(queryKeys.sessionArtifacts("p1", "s1"), opts.statuses);
  for (const [name, content] of Object.entries(opts.content ?? {})) {
    qc.setQueryData(queryKeys.artifact("p1", "s1", name), content);
  }
  return renderWithProviders(ui, {
    queryClient: qc,
    wrap: (children) => <TooltipProvider>{children}</TooltipProvider>,
  });
}

afterEach(() => {
  cleanup();
  toastMocks.success.mockReset();
  toastMocks.error.mockReset();
});

describe("parseChecklist", () => {
  it("parses the standard table format counting 'done' rows", () => {
    const body = `
| # | Task | Status |
|---|------|--------|
| 1 | A    | done   |
| 2 | B    | todo   |
| 3 | C    | done   |
`;
    expect(parseChecklist(body)).toMatchObject({ done: 2, total: 3 });
  });

  it("falls back to bullet checkboxes when no table is present", () => {
    expect(parseChecklist("- [x] one\n- [ ] two\n- [X] three")).toMatchObject({
      done: 2,
      total: 3,
    });
  });

  it("returns 0/0 when no rows found", () => {
    expect(parseChecklist("just some prose")).toEqual({
      done: 0,
      total: 0,
      rows: [],
    });
  });
});

describe("ArtifactList", () => {
  it("renders one tab per manifest entry in order, with missing ones greyed", () => {
    const { container } = renderWithCache(<ArtifactList projectId="p1" sessionId="s1" />, {
      manifest: fixtureManifest(),
      statuses: [
        statusFor("plan", true),
        statusFor("task-checklist", true),
        statusFor("handoff", false),
        statusFor("extra-1", true),
        statusFor("extra-2", false),
      ],
    });

    const tabs = container.querySelectorAll("[data-tab-name]");
    expect(tabs.length).toBe(5);
    expect((tabs[0] as HTMLElement).getAttribute("data-tab-name")).toBe("plan");
    expect((tabs[2] as HTMLElement).getAttribute("data-present")).toBe("false");
    expect((tabs[0] as HTMLElement).getAttribute("data-present")).toBe("true");
  });

  it("shows the 'not yet produced' tooltip hint for missing artifacts", () => {
    renderWithCache(<ArtifactList projectId="p1" sessionId="s1" />, {
      manifest: fixtureManifest(),
      statuses: [
        statusFor("plan", false),
        statusFor("task-checklist", false),
        statusFor("handoff", false),
        statusFor("extra-1", false),
        statusFor("extra-2", false),
      ],
    });

    // Default tab is "plan" which is missing — viewer shows empty state
    expect(screen.getByTestId("artifact-missing")).toBeInTheDocument();
    expect(screen.getByText(/sessions\/s1\/plan\.md/)).toBeInTheDocument();
  });

  it("renders the TaskChecklistRender progress bar for the task-checklist artifact", async () => {
    const content: Record<string, ArtifactContent> = {
      "task-checklist": {
        name: "task-checklist",
        file_path: "sessions/s1/task-checklist.md",
        body: "- [x] a\n- [ ] b\n- [x] c",
        mtime: "2026-04-24T00:00:00Z",
      },
    };
    renderWithCache(<ArtifactList projectId="p1" sessionId="s1" />, {
      manifest: { artifacts: [SPECS["task-checklist"]] },
      statuses: [statusFor("task-checklist", true)],
      content,
    });

    await waitFor(() => expect(screen.getByTestId("task-checklist-progress")).toBeInTheDocument());
    expect(screen.getByText("2/3")).toBeInTheDocument();
  });
});

describe("ArtifactViewer approval gate", () => {
  it("fires approve and shows a success toast", async () => {
    const content: ArtifactContent = {
      name: "plan",
      file_path: "sessions/s1/plan.md",
      body: "Plan body.",
      mtime: "2026-04-24T00:00:00Z",
    };

    const approveSpy = vi.fn();
    server.use(
      http.post("/api/projects/p1/sessions/s1/artifacts/plan/approve", ({ request }) => {
        approveSpy(request.url, request.method);
        return HttpResponse.json(statusFor("plan", true));
      }),
    );

    renderWithCache(
      <ArtifactViewer projectId="p1" sessionId="s1" name="plan" status={statusFor("plan", true)} />,
      {
        manifest: fixtureManifest(),
        statuses: [statusFor("plan", true)],
        content: { plan: content },
      },
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));

    await waitFor(() => expect(approveSpy).toHaveBeenCalled());
    expect(approveSpy.mock.calls[0]).toEqual([
      expect.stringContaining("/api/projects/p1/sessions/s1/artifacts/plan/approve"),
      "POST",
    ]);
    expect(toastMocks.success).toHaveBeenCalledWith("Artifact approved.");
  });

  it("requires feedback before rejecting, and shows an inline error if empty", async () => {
    const content: ArtifactContent = {
      name: "plan",
      file_path: "sessions/s1/plan.md",
      body: "Plan body.",
      mtime: "2026-04-24T00:00:00Z",
    };

    const rejectSpy = vi.fn();
    server.use(
      http.post("/api/projects/p1/sessions/s1/artifacts/plan/reject", ({ request }) => {
        rejectSpy(request.url, request.method);
        return HttpResponse.json(statusFor("plan", true));
      }),
    );

    renderWithCache(
      <ArtifactViewer projectId="p1" sessionId="s1" name="plan" status={statusFor("plan", true)} />,
      {
        manifest: fixtureManifest(),
        statuses: [statusFor("plan", true)],
        content: { plan: content },
      },
    );

    fireEvent.click(screen.getByRole("button", { name: /^Reject/ }));
    const sendBtn = await screen.findByRole("button", { name: /Send rejection/ });

    // Submit without feedback — should show inline error, no fetch call
    fireEvent.click(sendBtn);
    expect(await screen.findByRole("alert")).toHaveTextContent("Feedback is required");
    expect(rejectSpy).not.toHaveBeenCalled();

    // Fill in feedback and retry
    const textarea = screen.getByLabelText("Rejection feedback");
    fireEvent.change(textarea, { target: { value: "Please redo this." } });
    fireEvent.click(sendBtn);

    await waitFor(() => expect(rejectSpy).toHaveBeenCalled());
    expect(rejectSpy.mock.calls[0]).toEqual([
      expect.stringContaining("/api/projects/p1/sessions/s1/artifacts/plan/reject"),
      "POST",
    ]);
  });

  it("renders the recorded approval read-only when approval already exists", () => {
    const status: ArtifactStatus = makeArtifactStatus(SPECS.plan, true, {
      approval: {
        approved: true,
        reviewer: "sean",
        reviewed_at: "2026-04-20T12:00:00Z",
        feedback: "LGTM",
      },
    });
    const content: ArtifactContent = {
      name: "plan",
      file_path: "sessions/s1/plan.md",
      body: "Body.",
      mtime: "2026-04-24T00:00:00Z",
    };
    renderWithCache(<ArtifactViewer projectId="p1" sessionId="s1" name="plan" status={status} />, {
      manifest: fixtureManifest(),
      statuses: [status],
      content: { plan: content },
    });

    expect(screen.getByText(/Approved/)).toBeInTheDocument();
    expect(screen.getByText(/sean/)).toBeInTheDocument();
    expect(screen.getByText("LGTM")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke" })).toBeDisabled();
  });
});
