import { Stamp } from "@/components/ui/stamp";
import { cn } from "@/lib/utils";
import type { WorkflowValidator } from "@/lib/api/endpoints/workflow";

const CARD_W = 168;
const CARD_H = 78;

/**
 * Validator card rendered above the lifecycle wire on the workflow
 * map. Per [[validator-primitive]] the cognitive distinction from
 * [[tripwire-primitive]] is enforced visually:
 *
 *  - GREEN tone (gate stamp) signals "must pass — blocks event"
 *  - copy reads "blocks until {checks}" so a reader knows the rule
 *
 * The card is positioned by its midpoint (x, y); the SVG
 * foreignObject hosts the HTML chrome so the Stamp + Tailwind
 * classes carry across.
 */
export interface ValidatorCardProps {
  validator: WorkflowValidator;
  x: number;
  y: number;
  /** When true the card drops to ~25% opacity — used during hover-
   *  highlight on the canvas. */
  dimmed: boolean;
  onClick: () => void;
}

export function ValidatorCard({ validator, x, y, dimmed, onClick }: ValidatorCardProps) {
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
        aria-label={`Validator ${validator.name}`}
        className={cn(
          "flex h-full w-full flex-col items-start gap-1.5 rounded-(--radius-stamp)",
          "border border-(--color-gate) bg-(--color-paper) px-2.5 py-2 text-left",
          "transition-colors hover:bg-(--color-gate)/5",
        )}
      >
        <div className="flex items-center gap-1.5">
          <Stamp tone="gate" variant="status">
            GATE
          </Stamp>
          <span className="font-sans font-semibold text-[12px] text-(--color-ink) leading-tight">
            {validator.name}
          </span>
        </div>
        <span className="font-serif text-[11px] italic text-(--color-ink-2) leading-snug">
          blocks until {validator.checks ?? "verdict passes"}
        </span>
      </button>
    </foreignObject>
  );
}
