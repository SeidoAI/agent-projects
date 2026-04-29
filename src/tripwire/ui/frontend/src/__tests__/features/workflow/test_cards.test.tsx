import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArtifactCard } from "@/features/workflow/ArtifactCard";
import { ConnectorCurve } from "@/features/workflow/ConnectorCurve";
import { StationCard } from "@/features/workflow/StationCard";
import { TripwireCard } from "@/features/workflow/TripwireCard";
import { ValidatorCard } from "@/features/workflow/ValidatorCard";

function renderInSvg(node: React.ReactNode) {
  return render(
    <svg width="1380" height="820">
      <title>test canvas</title>
      {node}
    </svg>,
  );
}

describe("StationCard", () => {
  afterEach(cleanup);

  it("renders the ordinal + label using sessionStageColor for the dot", () => {
    renderInSvg(
      <StationCard
        station={{ id: "executing", n: 3, label: "executing", desc: "agents working" }}
        x={500}
        y={420}
      />,
    );
    expect(screen.getByText(/executing/i)).toBeTruthy();
    expect(screen.getByText("03")).toBeTruthy();
  });
});

describe("ValidatorCard", () => {
  afterEach(cleanup);

  it("renders the GATE stamp + name + 'blocks until' copy", () => {
    renderInSvg(
      <ValidatorCard
        validator={{
          id: "v1",
          kind: "gate",
          name: "self-review",
          fires_on_station: "in_review",
          checks: "self-review.md exists",
          blocks: true,
        }}
        x={500}
        y={300}
        dimmed={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText("GATE")).toBeTruthy();
    expect(screen.getByText("self-review")).toBeTruthy();
    expect(screen.getByText(/blocks until/i)).toBeTruthy();
  });

  it("invokes onClick when clicked", () => {
    const onClick = vi.fn();
    renderInSvg(
      <ValidatorCard
        validator={{
          id: "v1",
          kind: "gate",
          name: "self-review",
          fires_on_station: "in_review",
        }}
        x={500}
        y={300}
        dimmed={false}
        onClick={onClick}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /self-review/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("TripwireCard", () => {
  afterEach(cleanup);

  it("renders the TRIPWIRE stamp + name + 'fires on' copy + 'agent must ack'", () => {
    renderInSvg(
      <TripwireCard
        tripwire={{
          id: "t1",
          kind: "tripwire",
          name: "stale-context",
          fires_on_station: "in_review",
          fires_on_event: "session.complete",
        }}
        x={500}
        y={200}
        dimmed={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText("TRIPWIRE")).toBeTruthy();
    expect(screen.getByText("stale-context")).toBeTruthy();
    expect(screen.getByText(/fires on/i)).toBeTruthy();
    expect(screen.getByText(/agent must ack/i)).toBeTruthy();
  });
});

describe("ArtifactCard", () => {
  afterEach(cleanup);

  it("renders the ARTIFACT stamp + label", () => {
    renderInSvg(
      <ArtifactCard
        artifact={{
          id: "a_plan",
          label: "plan.md",
          produced_by: "queued",
          consumed_by: "executing",
        }}
        x={500}
        y={540}
        dimmed={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText("ARTIFACT")).toBeTruthy();
    expect(screen.getByText("plan.md")).toBeTruthy();
  });
});

describe("ConnectorCurve", () => {
  afterEach(cleanup);

  it("renders an SVG path with the supplied id and `d` derived from endpoints", () => {
    renderInSvg(
      <ConnectorCurve id="c1" from={{ x: 0, y: 100 }} to={{ x: 200, y: 420 }} dimmed={false} />,
    );
    const path = document.querySelector('[data-connector-id="c1"]') as SVGPathElement | null;
    expect(path).toBeTruthy();
    expect(path?.getAttribute("d")).toMatch(/^M0,100/);
  });

  it("drops opacity when dimmed=true", () => {
    renderInSvg(
      <ConnectorCurve id="c1" from={{ x: 0, y: 100 }} to={{ x: 200, y: 420 }} dimmed={true} />,
    );
    const path = document.querySelector('[data-connector-id="c1"]') as SVGPathElement | null;
    expect(Number(path?.getAttribute("opacity"))).toBeLessThan(0.5);
  });
});
