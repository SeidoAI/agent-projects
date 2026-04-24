import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: toastMocks.success, error: toastMocks.error },
}));

function baseManifest(): ArtifactManifest {
  return {
    artifacts: [
      {
        name: "plan",
        file: "plan.md",
        template: "plan",
        produced_at: "planning",
        produced_by: "pm",
        owned_by: null,
        required: true,
        approval_gate: true,
      },
      {
        name: "task-checklist",
        file: "task-checklist.md",
        template: "task-checklist",
        produced_at: "executing",
        produced_by: "executor",
        owned_by: null,
        required: true,
        approval_gate: false,
      },
      {
        name: "handoff",
        file: "handoff.yaml",
        template: "handoff",
        produced_at: "reviewing",
        produced_by: "agent",
        owned_by: null,
        required: false,
        approval_gate: false,
      },
      {
        name: "extra-1",
        file: "extra-1.md",
        template: "plain",
        produced_at: "executing",
        produced_by: "agent",
        owned_by: null,
        required: false,
        approval_gate: false,
      },
      {
        name: "extra-2",
        file: "extra-2.md",
        template: "plain",
        produced_at: "executing",
        produced_by: "agent",
        owned_by: null,
        required: false,
        approval_gate: false,
      },
    ],
  };
}

function makeStatus(name: string, present: boolean): ArtifactStatus {
  const spec = baseManifest().artifacts.find((a) => a.name === name);
  if (!spec) throw new Error(`Unknown artifact name in fixture: ${name}`);
  return {
    spec,
    present,
    size_bytes: present ? 120 : null,
    last_modified: present ? new Date().toISOString() : null,
    approval: null,
  };
}

function prime(opts: {
  manifest: ArtifactManifest;
  statuses: ArtifactStatus[];
  content?: Record<string, ArtifactContent>;
}): { wrapper: ({ children }: { children: ReactNode }) => ReactElement; qc: QueryClient } {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  qc.setQueryData(queryKeys.artifactManifest("p1"), opts.manifest);
  qc.setQueryData(queryKeys.sessionArtifacts("p1", "s1"), opts.statuses);
  for (const [name, content] of Object.entries(opts.content ?? {})) {
    qc.setQueryData(queryKeys.artifact("p1", "s1", name), content);
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TooltipProvider>{children}</TooltipProvider>
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
    const { wrapper } = prime({
      manifest: baseManifest(),
      statuses: [
        makeStatus("plan", true),
        makeStatus("task-checklist", true),
        makeStatus("handoff", false),
        makeStatus("extra-1", true),
        makeStatus("extra-2", false),
      ],
    });
    const { container } = render(<ArtifactList projectId="p1" sessionId="s1" />, { wrapper });

    const tabs = container.querySelectorAll("[data-tab-name]");
    expect(tabs.length).toBe(5);
    expect((tabs[0] as HTMLElement).getAttribute("data-tab-name")).toBe("plan");
    expect((tabs[2] as HTMLElement).getAttribute("data-present")).toBe("false");
    expect((tabs[0] as HTMLElement).getAttribute("data-present")).toBe("true");
  });

  it("shows the 'not yet produced' tooltip hint for missing artifacts", () => {
    const { wrapper } = prime({
      manifest: baseManifest(),
      statuses: [
        makeStatus("plan", false),
        makeStatus("task-checklist", false),
        makeStatus("handoff", false),
        makeStatus("extra-1", false),
        makeStatus("extra-2", false),
      ],
    });
    render(<ArtifactList projectId="p1" sessionId="s1" />, { wrapper });

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
        mtime: new Date().toISOString(),
      },
    };
    const { wrapper } = prime({
      manifest: {
        artifacts: [
          {
            name: "task-checklist",
            file: "task-checklist.md",
            template: "task-checklist",
            produced_at: "executing",
            produced_by: "executor",
            owned_by: null,
            required: true,
            approval_gate: false,
          },
        ],
      },
      statuses: [makeStatus("task-checklist", true)],
      content,
    });
    render(<ArtifactList projectId="p1" sessionId="s1" />, { wrapper });

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
      mtime: new Date().toISOString(),
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeStatus("plan", true)), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime({
      manifest: baseManifest(),
      statuses: [makeStatus("plan", true)],
      content: { plan: content },
    });
    render(
      <ArtifactViewer
        projectId="p1"
        sessionId="s1"
        name="plan"
        status={makeStatus("plan", true)}
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/p1/sessions/s1/artifacts/plan/approve",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(toastMocks.success).toHaveBeenCalledWith("Artifact approved.");
  });

  it("requires feedback before rejecting, and shows an inline error if empty", async () => {
    const content: ArtifactContent = {
      name: "plan",
      file_path: "sessions/s1/plan.md",
      body: "Plan body.",
      mtime: new Date().toISOString(),
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(makeStatus("plan", true)), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = prime({
      manifest: baseManifest(),
      statuses: [makeStatus("plan", true)],
      content: { plan: content },
    });
    render(
      <ArtifactViewer
        projectId="p1"
        sessionId="s1"
        name="plan"
        status={makeStatus("plan", true)}
      />,
      { wrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: /^Reject/ }));
    const sendBtn = await screen.findByRole("button", { name: /Send rejection/ });

    // Submit without feedback — should show inline error, no fetch call
    fireEvent.click(sendBtn);
    expect(await screen.findByRole("alert")).toHaveTextContent("Feedback is required");
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/reject"),
      expect.anything(),
    );

    // Fill in feedback and retry
    const textarea = screen.getByLabelText("Rejection feedback");
    fireEvent.change(textarea, { target: { value: "Please redo this." } });
    fireEvent.click(sendBtn);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/p1/sessions/s1/artifacts/plan/reject",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("renders the recorded approval read-only when approval already exists", () => {
    const status: ArtifactStatus = {
      ...makeStatus("plan", true),
      approval: {
        approved: true,
        reviewer: "sean",
        reviewed_at: "2026-04-20T12:00:00Z",
        feedback: "LGTM",
      },
    };
    const content: ArtifactContent = {
      name: "plan",
      file_path: "sessions/s1/plan.md",
      body: "Body.",
      mtime: new Date().toISOString(),
    };
    const { wrapper } = prime({
      manifest: baseManifest(),
      statuses: [status],
      content: { plan: content },
    });
    render(<ArtifactViewer projectId="p1" sessionId="s1" name="plan" status={status} />, {
      wrapper,
    });

    expect(screen.getByText(/Approved/)).toBeInTheDocument();
    expect(screen.getByText(/sean/)).toBeInTheDocument();
    expect(screen.getByText("LGTM")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke" })).toBeDisabled();
  });
});
