import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkflowDrawer } from "@/features/workflow/WorkflowDrawer";

describe("WorkflowDrawer", () => {
  it("renders status details", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "status",
          complexity: 4,
          entity: {
            id: "executing",
            label: "executing",
            next: { kind: "single", single: "in_review" },
            validators: [],
            jit_prompts: [],
            prompt_checks: [],
            artifacts: { produces: [], consumes: [] },
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("STATUS")).toBeInTheDocument();
    expect(screen.getByText(/4 declared controls/i)).toBeInTheDocument();
  });

  it("renders gate cluster members", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "gate",
          entity: {
            id: "in_review:gate",
            statusId: "in_review",
            blocking: true,
            validators: [{ id: "v_artifact_presence", label: "artifact presence" }],
            promptChecks: [{ id: "pm-session-review", label: "session review" }],
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("GATE")).toBeInTheDocument();
    expect(screen.getByText("v_artifact_presence")).toBeInTheDocument();
    expect(screen.getByText("pm-session-review")).toBeInTheDocument();
  });

  it("hides JIT prompt content for non-PM mode", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "jit_prompt",
          entity: {
            id: "self-review",
            label: "self review",
            status: "in_review",
            fires_on_event: "session.complete",
            prompt_revealed: "secret-prompt-body for the agent",
            prompt_redacted: "<<JIT prompt registered>>",
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("<<JIT prompt registered>>")).toBeInTheDocument();
    expect(screen.queryByText(/secret-prompt-body/i)).toBeNull();
  });

  it("reveals JIT prompt content for PM mode", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "jit_prompt",
          entity: {
            id: "self-review",
            label: "self review",
            status: "in_review",
            fires_on_event: "session.complete",
            prompt_revealed: "secret-prompt-body for the agent",
            prompt_redacted: "<<JIT prompt registered>>",
          },
        }}
        pmMode={true}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/secret-prompt-body for the agent/i)).toBeInTheDocument();
  });

  it("renders artifact details", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "artifact",
          statusId: "queued",
          direction: "produces",
          entity: { id: "plan", label: "plan.md", path: "sessions/{session_id}/plan.md" },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("ARTIFACT")).toBeInTheDocument();
    expect(screen.getByText("sessions/{session_id}/plan.md")).toBeInTheDocument();
  });

  it("renders drift details", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "drift",
          entity: {
            source: "definition",
            code: "workflow/unknown_next_status",
            workflow: "coding-session",
            status: "in_review",
            severity: "error",
            message: "missing target",
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("DRIFT")).toBeInTheDocument();
    expect(screen.getByText("missing target")).toBeInTheDocument();
  });

  it("renders nothing when selection is null", () => {
    const { container } = render(
      <WorkflowDrawer selection={null} pmMode={false} onClose={vi.fn()} />,
    );
    expect(container.querySelector("[role='dialog']")).toBeNull();
  });
});
