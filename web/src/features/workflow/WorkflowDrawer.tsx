import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { Stamp } from "@/components/ui/stamp";
import type {
  WorkflowArtifactRef,
  WorkflowRegistry,
  WorkflowRegistryEntry,
  WorkflowRoute,
  WorkflowStatus,
} from "@/lib/api/endpoints/workflow";

export type WorkflowSelection =
  | { kind: "status"; status: WorkflowStatus }
  | { kind: "route"; route: WorkflowRoute }
  | { kind: "jit_prompt"; id: string; statusId: string }
  | {
      kind: "artifact";
      artifact: WorkflowArtifactRef;
      statusId: string;
      direction: "produces" | "consumes";
    };

export interface WorkflowDrawerProps {
  selection: WorkflowSelection | null;
  registry?: WorkflowRegistry;
  pmMode: boolean;
  onClose: () => void;
}

export function WorkflowDrawer({
  selection,
  registry,
  pmMode,
  onClose,
}: WorkflowDrawerProps) {
  if (!selection) return null;
  const { title, header, body } = renderContents(selection, registry, pmMode);
  return (
    <EntityPreviewDrawer
      open
      onClose={onClose}
      title={title}
      headerSlot={header}
      body={body}
    />
  );
}

function renderContents(
  selection: WorkflowSelection,
  registry: WorkflowRegistry | undefined,
  pmMode: boolean,
): { title: string; header: React.ReactNode; body: React.ReactNode } {
  if (selection.kind === "status") {
    const s = selection.status;
    return {
      title: s.label ?? s.id,
      header: <Stamp tone="rule">STATUS</Stamp>,
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>status</strong> is a region of the workflow. Transitions are the border
            crossings into or out of this region.
          </DefinitionBlock>
          {s.description ? (
            <FieldBlock label="Description">
              <p className="font-serif text-[13px] italic text-(--color-ink-2)">
                {s.description}
              </p>
            </FieldBlock>
          ) : null}
          <FieldBlock label="Next">
            <pre className="whitespace-pre-wrap font-mono text-[12px] text-(--color-ink)">
              {JSON.stringify(s.next, null, 2)}
            </pre>
          </FieldBlock>
        </div>
      ),
    };
  }

  if (selection.kind === "route") {
    const r = selection.route;
    return {
      title: r.label,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="info">ROUTE</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            {r.actor} · {r.from} to {r.to}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>route</strong> is process movement across status territory. It owns actor,
            trigger, command, and branch meaning.
          </DefinitionBlock>
          <FieldBlock label="Kind">
            <span className="font-mono text-[12px] text-(--color-ink)">{r.kind}</span>
          </FieldBlock>
          <FieldBlock label="Trigger">
            <span className="font-mono text-[12px] text-(--color-ink-2)">
              {r.trigger ?? "-"}
            </span>
          </FieldBlock>
          {r.command ? (
            <FieldBlock label="Command">
              <span className="font-mono text-[12px] text-(--color-ink-2)">{r.command}</span>
            </FieldBlock>
          ) : null}
          {r.skills.length > 0 ? (
            <FieldBlock label="Skills">
              <ul className="flex flex-col gap-1">
                {r.skills.map((s) => (
                  <li key={s} className="font-mono text-[12px] text-(--color-ink)">
                    {s}
                  </li>
                ))}
              </ul>
            </FieldBlock>
          ) : null}
        </div>
      ),
    };
  }

  if (selection.kind === "jit_prompt") {
    const entry = (registry?.jit_prompts ?? []).find((p) => p.id === selection.id);
    const reveal = pmMode ? entry?.prompt_revealed : null;
    const placeholder = entry?.prompt_redacted ?? "<<JIT prompt registered>>";
    return {
      title: entry?.label ?? selection.id,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="tripwire">JIT PROMPT</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            status · {selection.statusId}
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
              {entry?.fires_on_event ?? "-"}
            </span>
          </FieldBlock>
          <FieldBlock label="Prompt">
            {reveal ? (
              <pre className="whitespace-pre-wrap font-mono text-[12px] text-(--color-ink)">
                {reveal}
              </pre>
            ) : (
              <p className="font-serif text-[13px] italic text-(--color-ink-3)">
                {placeholder}
              </p>
            )}
          </FieldBlock>
          {entry?.description ? (
            <FieldBlock label="Description">
              <p className="font-serif text-[13px] italic text-(--color-ink-2)">
                {entry.description}
              </p>
            </FieldBlock>
          ) : null}
        </div>
      ),
    };
  }

  // artifact
  const a = selection.artifact;
  return {
    title: a.label,
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
          <span className="font-mono text-[12px] text-(--color-ink)">{a.id}</span>
        </FieldBlock>
        <FieldBlock label="Path">
          <span className="font-mono text-[12px] text-(--color-ink-2)">{a.path ?? "-"}</span>
        </FieldBlock>
      </div>
    ),
  };
}

// Keep eslint happy if registry list element type is referenced.
export type { WorkflowRegistryEntry };

function DefinitionBlock({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-serif text-[14px] text-(--color-ink-2) leading-relaxed">{children}</p>
  );
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
