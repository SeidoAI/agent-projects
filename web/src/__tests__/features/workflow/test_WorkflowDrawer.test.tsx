import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowDrawer } from "@/features/workflow/WorkflowDrawer";

afterEach(cleanup);

describe("WorkflowDrawer — validator selection", () => {
  it("renders the GATE stamp + the rule it checks", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "validator",
          entity: {
            id: "v1",
            kind: "gate",
            name: "self-review",
            fires_on_station: "in_review",
            checks: "self-review.md exists in session bundle",
            blocks: true,
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("GATE")).toBeTruthy();
    expect(screen.getByRole("heading", { name: /self-review/i })).toBeTruthy();
    expect(screen.getByText(/self-review\.md exists in session bundle/i)).toBeTruthy();
  });
});

describe("WorkflowDrawer — JIT prompt selection redaction", () => {
  it("hides the prompt content for non-PM mode and shows the placeholder", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "jit_prompt",
          entity: {
            id: "t1",
            kind: "jit_prompt",
            name: "stale-context",
            fires_on_station: "in_review",
            fires_on_event: "session.complete",
            prompt_revealed: null,
            prompt_redacted: "<<JIT prompt registered>>",
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("<<JIT prompt registered>>")).toBeTruthy();
    expect(screen.queryByText(/secret-prompt-body/i)).toBeNull();
  });

  it("reveals the prompt content for PM-mode", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "jit_prompt",
          entity: {
            id: "t1",
            kind: "jit_prompt",
            name: "stale-context",
            fires_on_station: "in_review",
            fires_on_event: "session.complete",
            prompt_revealed: "secret-prompt-body for the agent",
            prompt_redacted: "<<JIT prompt registered>>",
          },
        }}
        pmMode={true}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/secret-prompt-body for the agent/i)).toBeTruthy();
  });
});

describe("WorkflowDrawer — artifact selection", () => {
  it("renders the artifact label + producer/consumer lineage", () => {
    render(
      <WorkflowDrawer
        selection={{
          kind: "artifact",
          entity: {
            id: "a_plan",
            label: "plan.md",
            produced_by: "queued",
            consumed_by: "executing",
          },
        }}
        pmMode={false}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: /plan\.md/i })).toBeTruthy();
    expect(screen.getByText(/produced by/i)).toBeTruthy();
    expect(screen.getByText(/queued/)).toBeTruthy();
    expect(screen.getByText(/consumed by/i)).toBeTruthy();
    expect(screen.getByText(/executing/)).toBeTruthy();
  });
});

describe("WorkflowDrawer — closed", () => {
  it("renders nothing when selection is null", () => {
    const { container } = render(
      <WorkflowDrawer selection={null} pmMode={false} onClose={vi.fn()} />,
    );
    expect(container.querySelector("[role='dialog']")).toBeNull();
  });
});
