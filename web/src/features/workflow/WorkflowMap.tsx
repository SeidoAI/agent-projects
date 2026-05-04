import { AlertTriangle, BellRing, FileText, GitBranch, ShieldCheck } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import { useWorkflow } from "@/lib/api/endpoints/workflow";
import { isPmMode } from "@/lib/role";
import {
  type ArtifactMarker,
  buildWorkflowTerritory,
  type GateCluster,
  type JitPromptMarker,
  type TerritoryStatus,
  type TransitionRoute,
  type WorkflowTerritory,
} from "./useWorkflowLayout";
import { WorkflowDrawer, type WorkflowSelection } from "./WorkflowDrawer";

export function WorkflowMap() {
  const { projectId } = useProjectShell();
  const [searchParams] = useSearchParams();
  const pmMode = useMemo(() => isPmMode(searchParams.get("role")), [searchParams]);
  const query = useWorkflow(projectId, { pmMode });
  const { data: graph, isPending, isError, error, refetch } = query;
  const [workflowId, setWorkflowId] = useState<string | undefined>();
  const territory = useMemo(
    () => (graph ? buildWorkflowTerritory(graph, workflowId) : null),
    [graph, workflowId],
  );
  const [selection, setSelection] = useState<WorkflowSelection | null>(null);

  const stateBranch: React.ReactNode = (() => {
    if (territory) {
      return (
        <WorkflowTerritoryView
          territory={territory}
          workflowIds={graph?.workflows.map((workflow) => workflow.id) ?? []}
          selectedWorkflowId={territory.workflow.id}
          onSelectWorkflow={setWorkflowId}
          onSelect={setSelection}
        />
      );
    }
    if (isPending) return <LoadingState />;
    if (isError && !is404(error)) return <ErrorState onRetry={() => void refetch()} />;
    return <EmptyState />;
  })();

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) leading-tight">
          Workflow
        </h1>
        <p className="font-serif text-[14px] italic text-(--color-ink-2) leading-snug">
          a map of status territory, transition borders, controls, and proof.
        </p>
      </header>
      <Legend />
      {stateBranch}
      <WorkflowDrawer selection={selection} pmMode={pmMode} onClose={() => setSelection(null)} />
    </div>
  );
}

function WorkflowTerritoryView({
  territory,
  workflowIds,
  selectedWorkflowId,
  onSelectWorkflow,
  onSelect,
}: {
  territory: WorkflowTerritory;
  workflowIds: string[];
  selectedWorkflowId: string;
  onSelectWorkflow: (workflowId: string) => void;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  return (
    <section
      aria-label="Workflow territory map"
      data-testid="workflow-territory"
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2)"
    >
      <WorkflowToolbar
        territory={territory}
        workflowIds={workflowIds}
        selectedWorkflowId={selectedWorkflowId}
        onSelectWorkflow={onSelectWorkflow}
      />
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="flex min-w-max flex-col gap-3 p-4">
          <CompassLabels />
          <div className="flex items-stretch gap-0 max-lg:min-w-0 max-lg:flex-col max-lg:gap-3">
            {territory.statuses.map((region, index) => (
              <Fragment key={region.status.id}>
                <StatusRegion region={region} onSelect={onSelect} />
                <TransitionBoundary
                  routes={territory.transitions.filter((route) => route.from === region.status.id)}
                  isLast={index === territory.statuses.length - 1}
                />
              </Fragment>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function WorkflowToolbar({
  territory,
  workflowIds,
  selectedWorkflowId,
  onSelectWorkflow,
}: {
  territory: WorkflowTerritory;
  workflowIds: string[];
  selectedWorkflowId: string;
  onSelectWorkflow: (workflowId: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-(--color-edge) bg-(--color-paper) px-4 py-3">
      <Stamp tone="rule">{territory.workflow.id}</Stamp>
      <span className="font-mono text-[11px] text-(--color-ink-3)">
        actor {territory.workflow.actor || "-"} · trigger {territory.workflow.trigger || "-"}
      </span>
      <span className="ml-auto font-mono text-[11px] text-(--color-ink-3)">
        {territory.statuses.length} statuses · {territory.transitions.length} transitions
      </span>
      {territory.drift.length > 0 ? (
        <Stamp tone="tripwire">{territory.drift.length} drift</Stamp>
      ) : null}
      {workflowIds.length > 1 ? (
        <fieldset className="flex min-w-0 gap-1">
          <legend className="sr-only">Workflow selector</legend>
          {workflowIds.map((workflowId) => (
            <button
              key={workflowId}
              type="button"
              onClick={() => onSelectWorkflow(workflowId)}
              className="rounded-(--radius-stamp) border border-(--color-edge) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-ink-2) data-[active=true]:border-(--color-ink) data-[active=true]:text-(--color-ink)"
              data-active={workflowId === selectedWorkflowId}
            >
              {workflowId}
            </button>
          ))}
        </fieldset>
      ) : null}
    </div>
  );
}

function CompassLabels() {
  return (
    <div className="grid grid-cols-[96px_1fr_96px] items-center gap-3 font-mono text-[10px] uppercase tracking-[0.08em] text-(--color-ink-3)">
      <span>west / intent</span>
      <div className="flex flex-col items-center gap-1">
        <span>control / governance</span>
        <div className="h-px w-full bg-(--color-edge)" />
      </div>
      <span className="text-right">east / closure</span>
    </div>
  );
}

function StatusRegion({
  region,
  onSelect,
}: {
  region: TerritoryStatus;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  const width = `${region.width}px`;
  return (
    <section
      aria-label={`Status ${region.status.id}`}
      data-testid={`status-region-${region.status.id}`}
      className="flex min-h-[360px] flex-col border-y border-l border-(--color-edge) bg-(--color-paper) max-lg:w-full max-lg:border-r"
      style={{ width }}
    >
      <div className="flex min-h-[96px] flex-col gap-2 border-b border-dashed border-(--color-edge) p-3">
        <ControlShelf region={region} onSelect={onSelect} />
      </div>
      <button
        type="button"
        onClick={() =>
          onSelect({
            kind: "status",
            entity: region.status,
            complexity: region.complexity,
          })
        }
        className="flex flex-1 flex-col items-start gap-3 px-3 py-4 text-left transition-colors hover:bg-(--color-paper-3)"
        aria-label={`Status ${region.status.id}`}
      >
        <div className="flex w-full items-start gap-2">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="font-sans text-[18px] font-semibold text-(--color-ink) leading-tight">
              {region.status.label ?? region.status.id}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-(--color-ink-3)">
              pressure {region.complexity}
            </span>
          </div>
          {region.drift.length > 0 ? (
            <span className="ml-auto inline-flex items-center gap-1 rounded-(--radius-stamp) border border-(--color-tripwire) px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-tripwire)">
              <AlertTriangle size={12} /> {region.drift.length}
            </span>
          ) : null}
        </div>
        <RouteSummary statusId={region.status.id} next={region.status.next} />
      </button>
      <div className="min-h-[88px] border-t border-dashed border-(--color-edge) p-3">
        <EvidenceShelf region={region} onSelect={onSelect} />
      </div>
    </section>
  );
}

function ControlShelf({
  region,
  onSelect,
}: {
  region: TerritoryStatus;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {region.gate ? <GateButton gate={region.gate} onSelect={onSelect} /> : null}
      {region.jitPrompts.map((marker) => (
        <JitPromptButton key={marker.id} marker={marker} onSelect={onSelect} />
      ))}
      {region.drift.map((finding) => (
        <button
          key={`${finding.code}:${finding.status}:${finding.message}`}
          type="button"
          onClick={() => onSelect({ kind: "drift", entity: finding })}
          className="inline-flex items-center gap-1 rounded-(--radius-stamp) border border-(--color-tripwire) bg-(--color-paper-2) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-tripwire)"
        >
          <AlertTriangle size={13} /> drift
        </button>
      ))}
    </div>
  );
}

function GateButton({
  gate,
  onSelect,
}: {
  gate: GateCluster;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  const total = gate.validators.length + gate.promptChecks.length;
  return (
    <button
      type="button"
      onClick={() => onSelect({ kind: "gate", entity: gate })}
      aria-label={`Gate into ${gate.statusId}`}
      className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-gate) bg-(--color-paper-2) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-gate)"
    >
      <ShieldCheck size={13} /> {total} gate{total === 1 ? "" : "s"}
    </button>
  );
}

function JitPromptButton({
  marker,
  onSelect,
}: {
  marker: JitPromptMarker;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect({ kind: "jit_prompt", entity: marker.prompt })}
      aria-label={`JIT prompt ${marker.prompt.label}`}
      className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-tripwire) bg-(--color-paper-2) px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-(--color-tripwire)"
    >
      <BellRing size={13} /> JIT
    </button>
  );
}

function EvidenceShelf({
  region,
  onSelect,
}: {
  region: TerritoryStatus;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  if (region.artifacts.length === 0) {
    return (
      <span className="font-serif text-[12px] italic text-(--color-ink-3)">no declared proof</span>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {region.artifacts.map((marker) => (
        <ArtifactButton key={marker.id} marker={marker} onSelect={onSelect} />
      ))}
    </div>
  );
}

function ArtifactButton({
  marker,
  onSelect,
}: {
  marker: ArtifactMarker;
  onSelect: (selection: WorkflowSelection) => void;
}) {
  return (
    <button
      type="button"
      onClick={() =>
        onSelect({
          kind: "artifact",
          entity: marker.artifact,
          statusId: marker.statusId,
          direction: marker.direction,
        })
      }
      aria-label={`Artifact ${marker.artifact.label}`}
      className="inline-flex max-w-full items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1 font-mono text-[11px] text-(--color-ink-2)"
    >
      <FileText size={13} />
      <span className="truncate">{marker.artifact.label}</span>
    </button>
  );
}

function RouteSummary({
  statusId,
  next,
}: {
  statusId: string;
  next: TerritoryStatus["status"]["next"];
}) {
  if (next.kind === "terminal") {
    return (
      <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-(--color-ink-3)">
        terminal boundary
      </span>
    );
  }
  if (next.kind === "single") {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-[12px] text-(--color-ink-2)">
        <GitBranch size={13} /> {statusId} to {next.single}
      </span>
    );
  }
  return (
    <div className="flex flex-col gap-1 font-mono text-[11px] text-(--color-ink-2)">
      {next.branches.map((branch) => (
        <span key={branchLabel(branch)} className="inline-flex items-center gap-1">
          <GitBranch size={13} /> {branchLabel(branch)}
        </span>
      ))}
    </div>
  );
}

function TransitionBoundary({ routes, isLast }: { routes: TransitionRoute[]; isLast: boolean }) {
  if (isLast) return null;
  const primary = routes[0];
  return (
    <div className="flex w-[64px] shrink-0 flex-col items-center justify-center border-y border-(--color-edge) bg-(--color-paper-2) max-lg:hidden">
      <div className="h-px w-full bg-(--color-rule)" />
      <div className="my-2 flex flex-col items-center gap-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-(--color-ink-3)">
          {primary?.kind ?? "route"}
        </span>
        {routes.length > 1 ? <Stamp tone="info">{routes.length}</Stamp> : null}
      </div>
      <div className="h-px w-full bg-(--color-rule)" />
    </div>
  );
}

function branchLabel(branch: { if: string; then: string } | { else: string }): string {
  if ("else" in branch) return `else to ${branch.else}`;
  return `if ${branch.if} to ${branch.then}`;
}

function Legend() {
  const chips: { label: string; tone: React.ComponentProps<typeof Stamp>["tone"] }[] = [
    { label: "STATUS", tone: "rule" },
    { label: "GATE", tone: "gate" },
    { label: "JIT PROMPT", tone: "tripwire" },
    { label: "ARTIFACT", tone: "info" },
    { label: "DRIFT", tone: "tripwire" },
  ];
  return (
    <section
      aria-label="Legend"
      className="flex flex-wrap items-center gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      {chips.map((chip) => (
        <Stamp key={chip.label} tone={chip.tone}>
          {chip.label}
        </Stamp>
      ))}
    </section>
  );
}

function is404(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

function StateFrame({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex flex-1 items-center justify-center rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) py-24"
      role="status"
    >
      {children}
    </div>
  );
}

function LoadingState() {
  return (
    <StateFrame>
      <p data-loading="workflow" className="font-serif text-[14px] italic text-(--color-ink-3)">
        Loading workflow...
      </p>
    </StateFrame>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <StateFrame>
      <div className="flex flex-col items-center gap-3">
        <p className="font-serif text-[14px] italic text-(--color-rule)">
          Couldn't load the workflow map.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-(--radius-stamp) border border-(--color-ink) bg-(--color-paper) px-3 py-1 font-mono text-[11px] uppercase tracking-[0.06em] text-(--color-ink) hover:bg-(--color-paper-3)"
        >
          Retry
        </button>
      </div>
    </StateFrame>
  );
}

function EmptyState() {
  return (
    <StateFrame>
      <p className="font-serif text-[14px] italic text-(--color-ink-3)">
        Workflow not yet available.
      </p>
    </StateFrame>
  );
}
