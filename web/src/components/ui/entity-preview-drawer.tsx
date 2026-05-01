import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Right-edge sliding drawer chrome shared across all entity previews
 * (inbox entries, sessions, issues, validators, tripwires, ...).
 *
 * Per `[[dec-shared-preview-drawer]]`: extracted from the inbox
 * preview drawer so S2's card-click flow + later wave-3 sessions all
 * speak the same visual language. Provides Radix-Dialog primitives
 * (focus trap, ESC handling, overlay click-to-dismiss); the consumer
 * supplies the title, body, and optional header / footer slots.
 *
 * The body is rendered as-is — consumers control padding + scroll
 * behaviour via their own wrappers when they need something other
 * than the default scrollable region.
 */
export interface EntityPreviewDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Plain string title — also used as the Radix Dialog Title for
   *  screen readers when no `headerSlot` is provided. */
  title: string;
  /** The drawer body. Rendered inside a scrollable column. */
  body: ReactNode;
  /** Slot above the title — typically a row of badges / tags / id
   *  stamps. Renders inside the header band. */
  headerSlot?: ReactNode;
  /** Slot at the bottom of the drawer — typically a primary action
   *  button + status copy. Sticky to the bottom edge. */
  footerSlot?: ReactNode;
  /** Optional accent above the title — e.g. a "↗ open full" link
   *  back to a dedicated detail screen. */
  topRightSlot?: ReactNode;
}

export function EntityPreviewDrawer({
  open,
  onClose,
  title,
  body,
  headerSlot,
  footerSlot,
  topRightSlot,
}: EntityPreviewDrawerProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            "fixed inset-0 z-50 bg-(--color-ink)/30",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            "fixed top-0 right-0 z-50 flex h-full w-full max-w-[520px] flex-col",
            "border-(--color-edge) border-l bg-(--color-paper) shadow-2xl",
            "data-[state=open]:animate-in data-[state=open]:slide-in-from-right",
            "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right",
          )}
          aria-describedby={undefined}
        >
          <header className="flex items-start justify-between gap-3 border-(--color-edge) border-b px-5 pt-4 pb-3">
            <div className="min-w-0 flex-1">
              {headerSlot ? <div className="mb-2">{headerSlot}</div> : null}
              <DialogPrimitive.Title asChild>
                <h2 className="m-0 font-sans font-semibold text-[20px] text-(--color-ink) leading-tight tracking-[-0.01em]">
                  {title}
                </h2>
              </DialogPrimitive.Title>
            </div>
            <div className="flex items-center gap-2">
              {topRightSlot}
              <button
                type="button"
                onClick={onClose}
                aria-label="Close preview"
                className="inline-flex h-7 w-7 items-center justify-center rounded-(--radius-stamp) text-(--color-ink-3) hover:bg-(--color-paper-3) hover:text-(--color-ink)"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </header>
          <div className="flex-1 overflow-y-auto px-5 py-4">{body}</div>
          {footerSlot ? (
            <footer className="flex items-center justify-between gap-3 border-(--color-edge) border-t bg-(--color-paper-2) px-5 py-3">
              {footerSlot}
            </footer>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
