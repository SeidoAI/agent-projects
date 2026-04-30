import { colorForKind } from "./GraphSidebar";

/**
 * Legend strip for the Concept Graph header (KUI-104).
 * Mirrors the workflow page's Legend strip: swatch + serif italic copy.
 *
 * Type swatches mirror `KIND_COLOR` in `GraphSidebar.tsx`: each
 * concept node is filled with its type's colour, so the legend has to
 * enumerate the same vocabulary or users can't decode the canvas.
 */

/** Distinct colour buckets, with the kinds that share each bucket. */
const TYPE_GROUPS: { kinds: string[]; sample: string }[] = [
  { kinds: ["schema", "service"], sample: "schema" },
  { kinds: ["endpoint", "contract"], sample: "endpoint" },
  { kinds: ["decision"], sample: "decision" },
  { kinds: ["requirement"], sample: "requirement" },
  { kinds: ["model"], sample: "model" },
  { kinds: ["custom"], sample: "custom" },
];

export function GraphLegend() {
  return (
    <section
      data-testid="graph-legend"
      aria-label="Legend"
      className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-4 py-3"
    >
      {TYPE_GROUPS.map((g) => (
        <LegendDot
          key={g.sample}
          color={colorForKind(g.sample)}
          label={g.kinds.join(" · ")}
          filled
        />
      ))}
      <span aria-hidden className="h-4 w-px shrink-0 bg-(--color-edge)" />
      <LegendDot color="#c8861f" dashed label="stale" />
      <LegendLine color="var(--color-edge)" label="cites" />
      <LegendLine color="var(--color-edge)" dashed label="related" />
    </section>
  );
}

function LegendDot({
  color,
  label,
  dashed,
  filled,
}: {
  color: string;
  label: string;
  dashed?: boolean;
  filled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="inline-block h-4 w-4 shrink-0 rounded-full"
        style={{
          border: `2px ${dashed ? "dashed" : "solid"} ${color}`,
          // Mirrors the canvas: type-coloured fill at 50% opacity (same
          // as `fillOpacity={0.5}` on unfocused circles in ConceptGraph),
          // border at full opacity. `color-mix` keeps the var() reference
          // so theme changes still propagate.
          backgroundColor: filled
            ? `color-mix(in srgb, ${color} 50%, transparent)`
            : undefined,
        }}
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
