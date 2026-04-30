/**
 * Legend strip for the Concept Graph header (KUI-104).
 * Mirrors the workflow page's Legend strip: swatch + serif italic copy.
 */
export function GraphLegend() {
  return (
    <section
      data-testid="graph-legend"
      aria-label="Legend"
      className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      <LegendDot color="var(--color-ink)" label="fresh concept" />
      <LegendDot color="#c8861f" dashed label="stale concept" />
      <LegendLine color="var(--color-edge)" label="cites" />
      <LegendLine color="var(--color-edge)" dashed label="related" />
    </section>
  );
}

function LegendDot({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="inline-block h-4 w-4 shrink-0 rounded-full"
        style={{ border: `2px ${dashed ? "dashed" : "solid"} ${color}` }}
      />
      <span className="font-serif text-[15px] italic text-(--color-ink-3) leading-snug">
        {label}
      </span>
    </div>
  );
}

function LegendLine({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="inline-block h-px w-6 shrink-0"
        style={{ borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}` }}
      />
      <span className="font-serif text-[15px] italic text-(--color-ink-3) leading-snug">
        {label}
      </span>
    </div>
  );
}
