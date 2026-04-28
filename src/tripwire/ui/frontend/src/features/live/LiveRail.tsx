import { ArrowRight, Cpu, DollarSign, Zap } from "lucide-react";

import { Stamp } from "@/components/ui/stamp";
import type { ProcessEvent } from "@/lib/api/endpoints/events";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { cn } from "@/lib/utils";
import { InterveneButton } from "./InterveneButton";

/**
 * Right rail of the Live Monitor (S7).
 *
 * Reads from the parent (`LiveMonitor`) which owns the data hook.
 * The rail is stateless — every signal it renders is a prop, so it
 * can be unit-tested without spinning up the WS / TanStack stack.
 *
 * Sections, top-to-bottom:
 *  - Cost ticker (mono, tabular-nums) — increments with each turn
 *  - Agent state — `session.current_state` from the runtime
 *  - Tripwire fires — agent-facing copy per
 *    [[dec-tripwires-are-agent-facing]]; no "alert" / "warning"
 *  - Cost-approval chip — surfaces an open `cost-approval` inbox
 *    entry; clicking opens the EntityPreviewDrawer (parent owns
 *    the dialog state)
 *  - INTERVENE button — the human's escape hatch
 */
export interface LiveRailProps {
  projectId: string;
  sessionId: string;
  status: string;
  costUsd: number;
  /** Last-known agent state from the orchestration runtime; null
   *  when the session has never reported a status message. */
  agentState: string | null;
  tripwireFires: ProcessEvent[];
  /** Open `cost-approval` inbox entry referencing this session, or
   *  null. The chip only renders when this is set. */
  costApprovalEntry: InboxItem | null;
  /** Click handler for the cost-approval chip — called with the
   *  inbox entry id so the parent can open the preview drawer. */
  onCostApprovalClick: (entryId: string) => void;
}

export function LiveRail({
  projectId,
  sessionId,
  status,
  costUsd,
  agentState,
  tripwireFires,
  costApprovalEntry,
  onCostApprovalClick,
}: LiveRailProps) {
  return (
    <aside className="flex w-[280px] shrink-0 flex-col gap-4 border-(--color-edge) border-l bg-(--color-paper-2) px-4 py-4">
      <CostTicker costUsd={costUsd} />
      <AgentState state={agentState} />
      <TripwireFires fires={tripwireFires} />
      {costApprovalEntry ? (
        <CostApprovalChip entry={costApprovalEntry} onClick={onCostApprovalClick} />
      ) : null}
      <div className="mt-auto pt-4">
        <InterveneButton projectId={projectId} sessionId={sessionId} status={status} />
      </div>
    </aside>
  );
}

function CostTicker({ costUsd }: { costUsd: number }) {
  return (
    <section>
      <Heading icon={<DollarSign className="h-3 w-3" aria-hidden />}>cost</Heading>
      <div
        data-testid="cost-ticker"
        className={cn(
          "mt-1 font-mono font-semibold text-[24px] text-(--color-ink) tabular-nums leading-none tracking-[-0.02em]",
        )}
      >
        ${costUsd.toFixed(2)}
      </div>
    </section>
  );
}

function AgentState({ state }: { state: string | null }) {
  return (
    <section data-testid="agent-state">
      <Heading icon={<Cpu className="h-3 w-3" aria-hidden />}>agent state</Heading>
      <div className="mt-1 font-mono text-[12px] text-(--color-ink-2) tracking-[0.04em]">
        {state ?? <span className="text-(--color-ink-3) italic">— no state reported yet</span>}
      </div>
    </section>
  );
}

function TripwireFires({ fires }: { fires: ProcessEvent[] }) {
  return (
    <section>
      <Heading icon={<Zap className="h-3 w-3" aria-hidden />}>tripwire fires</Heading>
      {fires.length === 0 ? (
        <div className="mt-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          none yet
        </div>
      ) : (
        <ol className="mt-1 flex flex-col gap-1.5">
          {fires.map((fire) => (
            <li
              key={fire.id}
              data-testid={`tripwire-fire-row-${fire.id}`}
              className="flex flex-col gap-0.5 rounded-(--radius-stamp) border border-(--color-rule)/40 bg-(--color-rule)/5 px-2 py-1.5"
            >
              <span className="font-mono text-[9px] text-(--color-rule) uppercase tracking-[0.18em]">
                agent received tripwire
              </span>
              <span className="font-mono text-[11px] text-(--color-ink) tracking-[0.04em]">
                {fire.tripwire_id ?? "(unnamed)"}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CostApprovalChip({
  entry,
  onClick,
}: {
  entry: InboxItem;
  onClick: (entryId: string) => void;
}) {
  return (
    <button
      type="button"
      data-testid="cost-approval-chip"
      onClick={() => onClick(entry.id)}
      className="flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-tripwire) bg-(--color-tripwire)/10 px-2.5 py-2 text-left transition-opacity hover:opacity-80"
    >
      <Stamp tone="tripwire" variant="status">
        inbox
      </Stamp>
      <span className="font-mono text-[10px] text-(--color-tripwire) uppercase tracking-[0.18em]">
        cost approval needed
      </span>
      <ArrowRight className="ml-auto h-3 w-3 text-(--color-tripwire)" aria-hidden />
    </button>
  );
}

function Heading({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
      {icon}
      <span>{children}</span>
    </div>
  );
}
