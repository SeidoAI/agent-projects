import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import {
  type WorkflowDefinition,
  type WorkflowGraph,
  useWorkflow,
} from "@/lib/api/endpoints/workflow";
import { isPmMode } from "@/lib/role";
import {
  type FlowSelection,
  WorkflowFlowchart,
} from "./WorkflowFlowchart";
import { WorkflowDrawer, type WorkflowSelection } from "./WorkflowDrawer";
import { WorkflowLegend } from "./WorkflowLegend";
import { WorkflowNavigator } from "./WorkflowNavigator";

const WF_PARAM = "wf";

export function WorkflowMap() {
  const { projectId } = useProjectShell();
  const [searchParams, setSearchParams] = useSearchParams();
  const pmMode = useMemo(() => isPmMode(searchParams.get("role")), [searchParams]);
  const query = useWorkflow(projectId, { pmMode });
  const { data: graph, isPending, isError, error, refetch } = query;
  const [selection, setSelection] = useState<WorkflowSelection | null>(null);

  const activeId = pickActiveWorkflow(graph, searchParams.get(WF_PARAM));
  const workflow = activeId
    ? graph?.workflows.find((w) => w.id === activeId)
    : undefined;

  const handlePick = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(WF_PARAM, id);
    setSearchParams(next, { replace: false });
    setSelection(null);
  };

  const handleSelect = (s: FlowSelection) => setSelection(s);

  const stateBranch: React.ReactNode = (() => {
    if (graph && workflow) {
      return (
        <WorkflowPage
          graph={graph}
          workflow={workflow}
          activeId={workflow.id}
          onPick={handlePick}
          onSelect={handleSelect}
        />
      );
    }
    if (isPending) return <LoadingState />;
    if (isError && !is404(error)) return <ErrorState onRetry={() => void refetch()} />;
    return <EmptyState />;
  })();

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {stateBranch}
      <WorkflowDrawer
        selection={selection}
        registry={graph?.registry}
        pmMode={pmMode}
        onClose={() => setSelection(null)}
      />
    </div>
  );
}

interface WorkflowPageProps {
  graph: WorkflowGraph;
  workflow: WorkflowDefinition;
  activeId: string;
  onPick: (id: string) => void;
  onSelect: (s: FlowSelection) => void;
}

function WorkflowPage({
  graph,
  workflow,
  activeId,
  onPick,
  onSelect,
}: WorkflowPageProps) {
  return (
    <section
      data-testid="workflow-page"
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto"
    >
      <WorkflowNavigator
        workflows={graph.workflows}
        activeId={activeId}
        onPick={onPick}
      />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-[780px] font-serif text-[15px] italic text-(--color-ink-2) leading-snug">
          {workflow.brief_description ?? ""}
        </p>
        <div className="flex flex-col items-end gap-1.5 font-mono text-[11px] text-(--color-ink-3)">
          <span>workflow.yaml · v0.9.6 · gate-as-diamond</span>
          <div className="flex gap-1.5">
            <Stamp tone="rule">DEFINITION</Stamp>
            <Stamp tone="default">
              {workflow.statuses.length} ST · {workflow.routes.length} RT
            </Stamp>
          </div>
        </div>
      </header>
      <WorkflowLegend />
      <div className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) p-3">
        <WorkflowFlowchart
          workflow={workflow}
          registry={graph.registry}
          gateMode="diamond"
          onSelect={onSelect}
        />
      </div>
    </section>
  );
}

function pickActiveWorkflow(
  graph: WorkflowGraph | undefined,
  paramId: string | null,
): string | undefined {
  if (!graph || graph.workflows.length === 0) return undefined;
  if (paramId && graph.workflows.some((w) => w.id === paramId)) return paramId;
  return graph.workflows[0]?.id;
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
      <p
        data-loading="workflow"
        className="font-serif text-[14px] italic text-(--color-ink-3)"
      >
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
