import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Italic Instrument Serif annotation primitive (per spec §3.1 C0.4).
 *
 * Used for reviewer comments, agent reflections, captions, and any
 * "voice" content that should read as commentary on the surrounding
 * structured information rather than as part of it.
 */
export function MarginNote({ className, children, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("font-serif text-[16px] italic text-(--color-ink-2) leading-snug", className)}
      {...rest}
    >
      {children}
    </span>
  );
}
