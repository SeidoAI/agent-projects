/**
 * Floating legend panel that sits at the bottom-left of the Concept
 * Graph canvas (KUI-104). Mirrors the four-row swatch grid from
 * `design_handoff_tripwire_redesign/screens/concept-graph.jsx`:
 * fresh / stale concept dots and cites / related edge styles.
 */
export function GraphLegend() {
  return (
    <div
      data-testid="graph-legend"
      className="pointer-events-none absolute bottom-3 left-3 grid grid-cols-2 items-center gap-x-4 gap-y-1.5 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-3.5 py-2.5 font-mono text-[10px] text-(--color-ink-2) tracking-[0.04em]"
    >
      <LegendDot color="var(--color-ink)" label="fresh concept" />
      <LegendDot color="#c8861f" dashed label="stale concept" />
      <LegendLine color="var(--color-edge)" label="cites" />
      <LegendLine color="var(--color-edge)" dashed label="related" />
    </div>
  );
}

function LegendDot({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        aria-hidden
        className="inline-block h-2.5 w-2.5 rounded-full bg-(--color-paper-2)"
        style={{
          border: `1.4px ${dashed ? "dashed" : "solid"} ${color}`,
        }}
      />
      <span>{label}</span>
    </div>
  );
}

function LegendLine({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        aria-hidden
        className="inline-block h-px w-4"
        style={{
          borderTop: `1.4px ${dashed ? "dashed" : "solid"} ${color}`,
        }}
      />
      <span>{label}</span>
    </div>
  );
}
