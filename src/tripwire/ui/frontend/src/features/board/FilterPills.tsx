import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Multi-select filter pill row that sits above the board's lifecycle
 * columns. Per spec §3.3 and the v0.8.x amendments:
 *
 * - Active pills render as filled `ink` 8% with a mono label.
 * - Pill dimensions are: agent, owner, age, blocked, and
 *   `has-blocked-inbox-entry` (the latter replaces the misframed
 *   `has-tripwires` pill — tripwires are agent-facing per
 *   `[[dec-tripwires-are-agent-facing]]`).
 *
 * State is owned by the parent (Board.tsx) via `useBoardFilters`,
 * which persists every change to the URL query string.
 */
export interface FilterPillsProps {
  agents: string[];
  owners: string[];
  ages: string[];
  selectedAgents: Set<string>;
  selectedOwners: Set<string>;
  selectedAges: Set<string>;
  hasBlockedInbox: boolean;
  blocked: boolean;
  onToggleAgent: (agent: string) => void;
  onToggleOwner: (owner: string) => void;
  onToggleAge: (age: string) => void;
  onToggleBlockedInbox: () => void;
  onToggleBlocked: () => void;
  onClearAll: () => void;
}

export function FilterPills({
  agents,
  owners,
  ages,
  selectedAgents,
  selectedOwners,
  selectedAges,
  hasBlockedInbox,
  blocked,
  onToggleAgent,
  onToggleOwner,
  onToggleAge,
  onToggleBlockedInbox,
  onToggleBlocked,
  onClearAll,
}: FilterPillsProps) {
  const anyActive =
    selectedAgents.size > 0 ||
    selectedOwners.size > 0 ||
    selectedAges.size > 0 ||
    hasBlockedInbox ||
    blocked;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-1 py-2">
      <PillGroup label="agent">
        {agents.map((a) => (
          <Pill
            key={a}
            label={a}
            active={selectedAgents.has(a)}
            onToggle={() => onToggleAgent(a)}
          />
        ))}
      </PillGroup>
      <PillGroup label="owner">
        {owners.map((o) => (
          <Pill
            key={o}
            label={o}
            active={selectedOwners.has(o)}
            onToggle={() => onToggleOwner(o)}
          />
        ))}
      </PillGroup>
      <PillGroup label="age">
        {ages.map((a) => (
          <Pill key={a} label={a} active={selectedAges.has(a)} onToggle={() => onToggleAge(a)} />
        ))}
      </PillGroup>
      <PillGroup label="state">
        <Pill
          label="open blocked inbox entry"
          active={hasBlockedInbox}
          onToggle={onToggleBlockedInbox}
        />
        <Pill label="blocked" active={blocked} onToggle={onToggleBlocked} />
      </PillGroup>
      {anyActive ? (
        <button
          type="button"
          onClick={onClearAll}
          aria-label="Clear filters"
          className="ml-auto inline-flex items-center gap-1 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em] hover:text-(--color-ink)"
        >
          <X className="h-3 w-3" aria-hidden />
          clear filters
        </button>
      ) : null}
    </div>
  );
}

function PillGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
        {label}
      </span>
      {children}
    </div>
  );
}

function Pill({
  label,
  active,
  onToggle,
}: {
  label: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center rounded-(--radius-stamp) border px-2 py-0.5 font-mono text-[11px] tracking-[0.04em] transition-colors",
        active
          ? "border-(--color-ink) bg-(--color-ink)/8 text-(--color-ink)"
          : "border-(--color-edge) bg-transparent text-(--color-ink-3) hover:border-(--color-ink-3) hover:text-(--color-ink)",
      )}
    >
      {label}
    </button>
  );
}
