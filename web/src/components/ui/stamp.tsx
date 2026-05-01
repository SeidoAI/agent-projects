import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Cream-palette identifier/tag primitive — replaces shadcn `<Badge>`.
 *
 * Per spec §3.1 C0.4, every status-y / id-ish chip in the new UI uses
 * Geist Mono, uppercase, with a thin 1px border in either ink or one of
 * the mood colours (gate / tripwire / info / rule).
 *
 * - `tone` selects the border + text colour.
 * - `variant` is reserved for future shape switches (the Tweaks panel
 *   exposes a `stamp shape` dimension that maps to this prop in v0.8.x).
 */
export type StampTone = "default" | "gate" | "tripwire" | "info" | "rule";
export type StampVariant = "status" | "identifier" | "numeric";

export interface StampProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StampTone;
  variant?: StampVariant;
}

const TONE_CLASS: Record<StampTone, string> = {
  default: "border-(--color-ink) text-(--color-ink)",
  gate: "border-(--color-gate) text-(--color-gate)",
  tripwire: "border-(--color-tripwire) text-(--color-tripwire)",
  info: "border-(--color-info) text-(--color-info)",
  rule: "border-(--color-rule) text-(--color-rule)",
};

export function Stamp({
  tone = "default",
  variant = "status",
  className,
  children,
  ...rest
}: StampProps) {
  return (
    <span
      data-tone={tone}
      data-variant={variant}
      className={cn(
        "inline-flex items-center gap-1 border px-1.5 py-0.5",
        "rounded-(--radius-stamp)",
        "font-mono text-[10px] font-semibold uppercase tracking-[0.06em] leading-none",
        "bg-transparent",
        TONE_CLASS[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
