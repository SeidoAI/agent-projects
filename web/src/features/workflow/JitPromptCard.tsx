import { Stamp } from "@/components/ui/stamp";
import type { WorkflowValidator } from "@/lib/api/endpoints/workflow";
import { cn } from "@/lib/utils";

const CARD_W = 184;
const CARD_H = 78;

/**
 * JIT prompt card rendered above the lifecycle wire on the workflow
 * map. Its visual contract is distinct from `ValidatorCard`:
 *
 *  - OCHRE tone signals "fires + nudges + agent
 *    must ack"
 *  - copy reads "fires on {event}; agent must ack" so a reader
 *    knows the lifecycle event that triggers it and what closes
 *    the loop
 *
 * Prompts content is intentionally hidden on the card — it lives
 * inside the drawer and is gated by PM-mode (server-side
 * redaction). This card is purely the registry surface ("a
 * JIT prompt exists here").
 */
export interface JitPromptCardProps {
  jitPrompt: WorkflowValidator;
  x: number;
  y: number;
  dimmed: boolean;
  onClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export function JitPromptCard({
  jitPrompt,
  x,
  y,
  dimmed,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: JitPromptCardProps) {
  return (
    <foreignObject
      x={x - CARD_W / 2}
      y={y - CARD_H / 2}
      width={CARD_W}
      height={CARD_H}
      opacity={dimmed ? 0.25 : 1}
      style={{ transition: "opacity 120ms ease-out", overflow: "visible" }}
    >
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        aria-label={`JIT prompt ${jitPrompt.name}`}
        className={cn(
          "flex h-full w-full flex-col items-start gap-1.5 rounded-(--radius-stamp)",
          "border border-(--color-tripwire) bg-(--color-paper) px-2.5 py-2 text-left",
          "transition-colors hover:bg-(--color-tripwire)/5",
        )}
      >
        <div className="flex items-center gap-1.5">
          <Stamp tone="tripwire" variant="status">
            JIT PROMPT
          </Stamp>
          <span className="font-sans font-semibold text-[12px] text-(--color-ink) leading-tight">
            {jitPrompt.name}
          </span>
        </div>
        <span className="font-serif text-[11px] italic text-(--color-ink-2) leading-snug">
          fires on <span className="font-mono not-italic">{jitPrompt.fires_on_event ?? "—"}</span> —
          agent must ack
        </span>
      </button>
    </foreignObject>
  );
}
