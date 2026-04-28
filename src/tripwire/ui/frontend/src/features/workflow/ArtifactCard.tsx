import { Stamp } from "@/components/ui/stamp";
import { cn } from "@/lib/utils";
import type { WorkflowArtifact } from "@/lib/api/endpoints/workflow";

const CARD_W = 156;
const CARD_H = 60;

/**
 * Artifact card rendered below the lifecycle wire — typed
 * documents the workflow produces (plan.md, self-review.md,
 * verification-checklist.md, ...). Click opens the drawer with
 * the most recent rendered instance from a real session.
 */
export interface ArtifactCardProps {
  artifact: WorkflowArtifact;
  x: number;
  y: number;
  dimmed: boolean;
  onClick: () => void;
}

export function ArtifactCard({ artifact, x, y, dimmed, onClick }: ArtifactCardProps) {
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
        aria-label={`Artifact ${artifact.label}`}
        className={cn(
          "flex h-full w-full flex-col items-start gap-1 rounded-(--radius-stamp)",
          "border border-(--color-edge) bg-(--color-paper-2) px-2.5 py-2 text-left",
          "transition-colors hover:border-(--color-ink-3)",
        )}
      >
        <Stamp tone="info" variant="identifier">
          ARTIFACT
        </Stamp>
        <span className="font-mono text-[12px] text-(--color-ink) leading-tight">
          {artifact.label}
        </span>
      </button>
    </foreignObject>
  );
}
