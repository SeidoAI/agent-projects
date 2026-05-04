import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { Stamp } from "@/components/ui/stamp";
import type {
  WorkflowArtifactRef,
  WorkflowDriftFinding,
  WorkflowRegistryEntry,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";
import type { GateCluster } from "./useWorkflowLayout";

export type WorkflowSelection =
  | { kind: "status"; entity: WorkflowStatus; complexity: number }
  | { kind: "gate"; entity: GateCluster }
  | { kind: "jit_prompt"; entity: WorkflowRegistryEntry }
  | {
      kind: "artifact";
      entity: WorkflowArtifactRef;
      statusId: string;
      direction: "produces" | "consumes";
    }
  | { kind: "drift"; entity: WorkflowDriftFinding };

export interface WorkflowDrawerProps {
  selection: WorkflowSelection | null;
  pmMode: boolean;
  onClose: () => void;
}

export function WorkflowDrawer({ selection, pmMode, onClose }: WorkflowDrawerProps) {
  if (!selection) return null;
  const { title, header, body } = renderContents(selection, pmMode);
  return (
    <EntityPreviewDrawer open onClose={onClose} title={title} headerSlot={header} body={body} />
  );
}

function renderContents(
  selection: WorkflowSelection,
  pmMode: boolean,
): { title: string; header: React.ReactNode; body: React.ReactNode } {
  if (selection.kind === "status") {
    const status = selection.entity;
    return {
      title: status.label ?? status.id,
      header: <Stamp tone="rule">STATUS</Stamp>,
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>status</strong> is a region of the workflow. Transitions are the border
            crossings into or out of this region.
          </DefinitionBlock>
          <FieldBlock label="Static pressure">
            <span className="font-mono text-[12px] text-(--color-ink)">
              {selection.complexity} declared controls, artifacts, or routes
            </span>
          </FieldBlock>
          <FieldBlock label="Next">
            <pre className="whitespace-pre-wrap font-mono text-[12px] text-(--color-ink)">
              {JSON.stringify(status.next, null, 2)}
            </pre>
          </FieldBlock>
        </div>
      ),
    };
  }

  if (selection.kind === "gate") {
    const gate = selection.entity;
    return {
      title: `Gate into ${gate.statusId}`,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="gate">GATE</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            status · {gate.statusId}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>gate cluster</strong> groups controls that evaluate the attempted status
            change. The first read is the cluster; the drawer carries the full member list.
          </DefinitionBlock>
          <ControlList title="Validators" entries={gate.validators} />
          <ControlList title="Prompt checks" entries={gate.promptChecks} />
        </div>
      ),
    };
  }

  if (selection.kind === "jit_prompt") {
    const prompt = selection.entity;
    const reveal = pmMode ? prompt.prompt_revealed : null;
    const placeholder = prompt.prompt_redacted ?? "<<JIT prompt registered>>";
    return {
      title: prompt.label,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="tripwire">JIT PROMPT</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            status · {prompt.status ?? "unmapped"}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>JIT prompt</strong> is an intervention. It injects attention at the moment
            recency matters; it is visually separate from gates.
          </DefinitionBlock>
          <FieldBlock label="Fires on">
            <span className="font-mono text-[12px] text-(--color-ink)">
              {prompt.fires_on_event ?? "-"}
            </span>
          </FieldBlock>
          <FieldBlock label="Prompt">
            {reveal ? (
              <pre className="whitespace-pre-wrap font-mono text-[12px] text-(--color-ink)">
                {reveal}
              </pre>
            ) : (
              <p className="font-serif text-[13px] italic text-(--color-ink-3)">{placeholder}</p>
            )}
          </FieldBlock>
        </div>
      ),
    };
  }

  if (selection.kind === "artifact") {
    const artifact = selection.entity;
    return {
      title: artifact.label,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="info">ARTIFACT</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            {selection.direction} · {selection.statusId}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            An <strong>artifact</strong> is proof declared by the workflow definition, not a live
            file discovered by the UI.
          </DefinitionBlock>
          <FieldBlock label="ID">
            <span className="font-mono text-[12px] text-(--color-ink)">{artifact.id}</span>
          </FieldBlock>
          <FieldBlock label="Path">
            <span className="font-mono text-[12px] text-(--color-ink-2)">
              {artifact.path ?? "-"}
            </span>
          </FieldBlock>
        </div>
      ),
    };
  }

  const finding = selection.entity;
  return {
    title: finding.code,
    header: (
      <div className="flex items-center gap-2">
        <Stamp tone={finding.severity === "error" ? "tripwire" : "info"}>DRIFT</Stamp>
        <span className="font-mono text-[11px] text-(--color-ink-3)">
          {finding.workflow}:{finding.status ?? "-"}
        </span>
      </div>
    ),
    body: (
      <div className="flex flex-col gap-4">
        <DefinitionBlock>
          Drift marks a definition-integrity problem: the workflow map and the implementation
          disagree, or runtime events bypassed the declared route.
        </DefinitionBlock>
        <FieldBlock label="Message">
          <p className="font-sans text-[13px] leading-snug text-(--color-ink-2)">
            {finding.message}
          </p>
        </FieldBlock>
      </div>
    ),
  };
}

function ControlList({ title, entries }: { title: string; entries: WorkflowRegistryEntry[] }) {
  if (entries.length === 0) {
    return (
      <FieldBlock label={title}>
        <p className="font-serif text-[13px] italic text-(--color-ink-3)">none</p>
      </FieldBlock>
    );
  }
  return (
    <FieldBlock label={title}>
      <ul className="flex flex-col gap-2">
        {entries.map((entry) => (
          <li key={entry.id} className="font-mono text-[12px] text-(--color-ink)">
            {entry.id}
            {entry.description ? (
              <span className="ml-2 font-serif text-[12px] italic text-(--color-ink-3)">
                {entry.description}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </FieldBlock>
  );
}

function DefinitionBlock({ children }: { children: React.ReactNode }) {
  return <p className="font-serif text-[14px] text-(--color-ink-2) leading-relaxed">{children}</p>;
}

function FieldBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-(--color-ink-3)">
        {label}
      </span>
      {children}
    </div>
  );
}
