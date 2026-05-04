import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectPicker } from "@/features/projects/ProjectPicker";
import type { ProjectSummary } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

function makeProject(overrides: Partial<ProjectSummary>): ProjectSummary {
  return {
    id: "p1",
    name: "project-tripwire-v0",
    key_prefix: "KUI",
    dir: "/Users/maia/Code/seido/tripwire/projects/project-tripwire-v0",
    phase: "executing",
    issue_count: 12,
    node_count: 34,
    session_count: 5,
    ...overrides,
  };
}

describe("ProjectPicker", () => {
  it("shows project paths in the selector list", () => {
    const queryClient = makeTestQueryClient();
    queryClient.setQueryData(queryKeys.projects(), [
      makeProject({ id: "p1" }),
      makeProject({
        id: "p2",
        name: "project-competitor-analysis",
        key_prefix: "CMP",
        dir: "/Users/maia/Code/seido/tripwire/projects/project-competitor-analysis",
      }),
    ]);

    renderWithProviders(<ProjectPicker />, { queryClient });

    expect(screen.getByText("tripwire-v0")).toBeInTheDocument();
    expect(
      screen.getByText("/Users/maia/Code/seido/tripwire/projects/project-tripwire-v0"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("/Users/maia/Code/seido/tripwire/projects/project-competitor-analysis"),
    ).toBeInTheDocument();
  });
});
