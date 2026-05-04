import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import {
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

const FOCUS_PARAM = "focus";

export function WorkflowMap() {
  const { projectId } = useProjectShell();
  const [searchParams, setSearchParams] = useSearchParams();
  const pmMode = useMemo(() => isPmMode(searchParams.get("role")), [searchParams]);
  const query = useWorkflow(projectId, { pmMode });
  const { data: graph, isPending, isError, error, refetch } = query;
  const [selection, setSelection] = useState<WorkflowSelection | null>(null);

  const focusId = pickFocus(graph, searchParams.get(FOCUS_PARAM));

  const handlePick = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(FOCUS_PARAM, id);
    setSearchParams(next, { replace: false });
    setSelection(null);
  };

  const handleSelect = (s: FlowSelection) => {
    if (!graph) return;
    if (s.kind === "work_step") {
      const wf = graph.workflows.find((w) => w.id === s.workflowId);
      const status = wf?.statuses.find((st) => st.id === s.statusId);
      const ws = status?.work_steps.find((w) => w.id === s.workStepId);
      if (!ws) return;
      setSelection({ kind: "work_step", statusId: s.statusId, workStep: ws });
      return;
    }
    if (s.kind === "status") {
      setSelection({ kind: "status", status: s.status });
      return;
    }
    if (s.kind === "route") {
      setSelection({ kind: "route", route: s.route });
      return;
    }
    if (s.kind === "jit_prompt") {
      setSelection({ kind: "jit_prompt", id: s.id, statusId: s.statusId });
      return;
    }
    setSelection({
      kind: "artifact",
      artifact: s.artifact,
      statusId: s.statusId,
      direction: s.direction,
    });
  };

  const stateBranch: React.ReactNode = (() => {
    if (graph && graph.workflows.length > 0) {
      return (
        <WorkflowPage
          graph={graph}
          focusId={focusId}
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
  focusId: string | null;
  onPick: (id: string) => void;
  onSelect: (s: FlowSelection) => void;
}

function WorkflowPage({ graph, focusId, onPick, onSelect }: WorkflowPageProps) {
  return (
    <section
      data-testid="workflow-page"
      className="flex min-h-0 flex-1 flex-col gap-3"
    >
      <WorkflowNavigator
        workflows={graph.workflows}
        activeId={focusId}
        onPick={onPick}
      />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[780px]">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-(--color-ink-3)">
            workflow map · {graph.workflows.length} workflows
          </div>
          <p className="mt-1 font-serif text-[15px] italic text-(--color-ink-2) leading-snug">
            All workflows on one canvas. Use the navigator to jump between bands;
            cross-workflow handoffs render as dashed indigo links.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5 font-mono text-[11px] text-(--color-ink-3)">
          <span>workflow.yaml · v0.9.6 · unified</span>
          <div className="flex gap-1.5">
            <Stamp tone="rule">DEFINITION</Stamp>
            <Stamp tone="default">
              {totalStatuses(graph)} ST · {totalRoutes(graph)} RT
            </Stamp>
          </div>
        </div>
      </header>
      <WorkflowLegend />
      <div className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) p-3">
        <WorkflowFlowchart
          graph={graph}
          focusId={focusId}
          registry={graph.registry}
          gateMode="diamond"
          onSelect={onSelect}
        />
      </div>
    </section>
  );
}

function totalStatuses(graph: WorkflowGraph): number {
  return graph.workflows.reduce((n, w) => n + w.statuses.length, 0);
}

function totalRoutes(graph: WorkflowGraph): number {
  return graph.workflows.reduce((n, w) => n + w.routes.length, 0);
}

function pickFocus(
  graph: WorkflowGraph | undefined,
  paramId: string | null,
): string | null {
  if (!graph || graph.workflows.length === 0) return null;
  if (paramId && graph.workflows.some((w) => w.id === paramId)) return paramId;
  return graph.workflows[0]?.id ?? null;
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
