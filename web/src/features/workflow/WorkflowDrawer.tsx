import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { Stamp } from "@/components/ui/stamp";
import type { WorkflowArtifact, WorkflowValidator } from "@/lib/api/endpoints/workflow";

/**
 * Tagged union of the things the workflow map opens a drawer for.
 * Stations are not included — the workflow map is the spec, and
 * stations are described by the legend strip + the canonical
 * [[session-stage-mapping]]; clicking them adds noise.
 */
export type WorkflowSelection =
  | { kind: "validator"; entity: WorkflowValidator }
  | { kind: "jit_prompt"; entity: WorkflowValidator }
  | { kind: "artifact"; entity: WorkflowArtifact };

export interface WorkflowDrawerProps {
  selection: WorkflowSelection | null;
  /** Whether the current viewer is in PM-mode. Drives whether the
   *  JIT prompt drawer reveals `prompt_revealed` content. The server
   *  is the source of truth (it nulls out `prompt_revealed` for
   *  non-PM viewers) — this flag is the UI-side belt-and-braces
   *  so we don't accidentally show a leaked value. */
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
  if (selection.kind === "validator") {
    const v = selection.entity;
    return {
      title: v.name,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="gate">GATE</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            station · {v.fires_on_station}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>validator</strong> blocks the lifecycle event until its rule passes.
            Validators are pass/fail; agents satisfy them by changing the project state and
            re-running the check.
          </DefinitionBlock>
          <FieldBlock label="Rule it checks">
            <span className="font-mono text-[12px] text-(--color-ink) leading-snug">
              {v.checks ?? "—"}
            </span>
          </FieldBlock>
          <FieldBlock label="Recent runs">
            <p className="font-serif text-[13px] italic text-(--color-ink-3)">
              See the Events log for the full history of this validator.
            </p>
          </FieldBlock>
        </div>
      ),
    };
  }
  if (selection.kind === "jit_prompt") {
    const t = selection.entity;
    const reveal = pmMode ? t.prompt_revealed : null;
    const placeholder = t.prompt_redacted ?? "<<JIT prompt registered>>";
    return {
      title: t.name,
      header: (
        <div className="flex items-center gap-2">
          <Stamp tone="tripwire">JIT PROMPT</Stamp>
          <span className="font-mono text-[11px] text-(--color-ink-3)">
            station · {t.fires_on_station}
          </span>
        </div>
      ),
      body: (
        <div className="flex flex-col gap-4">
          <DefinitionBlock>
            A <strong>JIT prompt</strong> fires on a lifecycle event with agent-facing instructions.
            The agent must <em>acknowledge</em> the prompt (act on it, then `--ack`) before the
            event proceeds.
          </DefinitionBlock>
          <FieldBlock label="Fires on">
            <span className="font-mono text-[12px] text-(--color-ink)">
              {t.fires_on_event ?? "—"}
            </span>
          </FieldBlock>
          <FieldBlock label="Agent prompt">
            {reveal ? (
              <pre className="whitespace-pre-wrap font-mono text-[12px] text-(--color-ink) leading-snug">
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
  const a = selection.entity;
  return {
    title: a.label,
    header: (
      <div className="flex items-center gap-2">
        <Stamp tone="info">ARTIFACT</Stamp>
      </div>
    ),
    body: (
      <div className="flex flex-col gap-4">
        <DefinitionBlock>
          An <strong>artifact</strong> is a typed document the workflow produces and another stage
          may consume. Authoring is the agent's job; structure is enforced by validators.
        </DefinitionBlock>
        <FieldBlock label="Lineage">
          <p className="font-mono text-[12px] text-(--color-ink) leading-snug">
            produced by <span className="font-semibold">{a.produced_by}</span>
            {a.consumed_by ? (
              <>
                {" "}
                · consumed by <span className="font-semibold">{a.consumed_by}</span>
              </>
            ) : null}
          </p>
        </FieldBlock>
        <FieldBlock label="Most recent instance">
          <p className="font-serif text-[13px] italic text-(--color-ink-3)">
            Open a session that produced this artifact to view the rendered markdown.
          </p>
        </FieldBlock>
      </div>
    ),
  };
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
