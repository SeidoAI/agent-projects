import { Check, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { cn } from "@/lib/utils";

/**
 * Two-bucket attention inbox — the leftmost dashboard column.
 *
 * The PM agent (and only the PM agent) curates entries here when
 * something needs the human's attention. Two buckets so the
 * cognitive treatment differs:
 *
 * - **BLOCKED** is interruptive — something is paused or about to
 *   drift without your call. Always-expanded; can't be collapsed.
 * - **FYI** is digest — decisions made, things completed; you
 *   should know in case you disagree. Collapsible chevron;
 *   default-expanded but can be rolled up after a skim.
 *
 * Clicking an item opens the EntityPreviewDrawer with the full
 * markdown body + references chip strip + resolve button. The
 * one-click ✓ in the row corner is a shortcut for the resolve
 * action without opening the drawer.
 */

export interface AttentionQueueProps {
  items: InboxItem[];
  /** Called when the user clicks the ✓ on a row (resolve shortcut). */
  onResolve?: (id: string) => void;
  /** Called when the user clicks anywhere else on a row — opens
   *  the preview drawer for the full body + references view. */
  onSelectItem?: (id: string) => void;
  className?: string;
}

export function AttentionQueue({ items, onResolve, onSelectItem, className }: AttentionQueueProps) {
  const blocked = items.filter((i) => i.bucket === "blocked" && !i.resolved);
  const fyi = items.filter((i) => i.bucket === "fyi" && !i.resolved);

  return (
    <section
      className={cn(
        "flex flex-col gap-3 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-4",
        className,
      )}
    >
      <BlockedPanel items={blocked} onResolve={onResolve} onSelectItem={onSelectItem} />
      <FyiPanel items={fyi} onResolve={onResolve} onSelectItem={onSelectItem} />
    </section>
  );
}

interface PanelProps {
  items: InboxItem[];
  onResolve?: (id: string) => void;
  onSelectItem?: (id: string) => void;
}

function BlockedPanel({ items, onResolve, onSelectItem }: PanelProps) {
  // Always-expanded — blocked items are urgent enough that hiding
  // them would defeat the point. Empty state stays visible so the
  // PM gets active reassurance ("nothing blocking you right now").
  return (
    <div>
      <PanelHeader
        label="blocked"
        sub="needs you"
        count={items.length}
        tone="alert"
        collapsible={false}
      />
      {items.length === 0 ? (
        <Empty>nothing blocking you right now</Empty>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <ItemRow item={item} onResolve={onResolve} onSelectItem={onSelectItem} tone="alert" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FyiPanel({ items, onResolve, onSelectItem }: PanelProps) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-(--color-edge) border-t pt-3">
      <PanelHeader
        label="fyi"
        sub="happened"
        count={items.length}
        tone="muted"
        collapsible
        open={open}
        onToggle={() => setOpen((o) => !o)}
      />
      {open ? (
        items.length === 0 ? (
          <Empty>no recent decisions</Empty>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {items.map((item) => (
              <li key={item.id}>
                <ItemRow
                  item={item}
                  onResolve={onResolve}
                  onSelectItem={onSelectItem}
                  tone="muted"
                />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}

interface PanelHeaderProps {
  label: string;
  sub: string;
  count: number;
  tone: "alert" | "muted";
  collapsible: boolean;
  open?: boolean;
  onToggle?: () => void;
}

function PanelHeader({ label, sub, count, tone, collapsible, open, onToggle }: PanelHeaderProps) {
  const labelClass =
    tone === "alert"
      ? "font-mono text-[11px] font-semibold text-(--color-rule) uppercase tracking-[0.18em]"
      : "font-mono text-[11px] font-semibold text-(--color-ink-3) uppercase tracking-[0.18em]";
  const inner = (
    <>
      <div className="flex items-baseline gap-2">
        <span className={labelClass}>{label}</span>
        <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
          · {sub} ({count})
        </span>
      </div>
      {collapsible ? (
        open ? (
          <ChevronUp className="h-3.5 w-3.5 text-(--color-ink-3)" aria-hidden />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-(--color-ink-3)" aria-hidden />
        )
      ) : null}
    </>
  );
  if (collapsible && onToggle) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2"
      >
        {inner}
      </button>
    );
  }
  return <div className="flex items-center justify-between gap-2">{inner}</div>;
}

interface ItemRowProps {
  item: InboxItem;
  tone: "alert" | "muted";
  onResolve?: (id: string) => void;
  onSelectItem?: (id: string) => void;
}

function ItemRow({ item, tone, onResolve, onSelectItem }: ItemRowProps) {
  const containerClass =
    tone === "alert"
      ? "block w-full text-left rounded-(--radius-stamp) border border-(--color-rule)/60 bg-(--color-rule)/5 px-3 py-2 transition-colors hover:border-(--color-rule)"
      : "block w-full text-left rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 transition-colors hover:border-(--color-ink-3)";
  const titleClass =
    tone === "alert"
      ? "font-sans text-[13px] font-medium text-(--color-ink) leading-snug"
      : "font-sans text-[13px] text-(--color-ink) leading-snug";
  const handleClick = () => onSelectItem?.(item.id);
  return (
    <div className="relative">
      <button type="button" onClick={handleClick} className={containerClass}>
        <div className={titleClass}>{item.title}</div>
        {item.body?.trim() ? (
          <div className="mt-0.5 line-clamp-2 font-sans text-[12px] text-(--color-ink-2) leading-snug">
            {firstLine(item.body)}
          </div>
        ) : null}
        {item.references.length > 0 ? (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {item.references.map((ref, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: refs have no stable id; positional ok for static list
              <ReferenceChip key={i} reference={ref} />
            ))}
          </div>
        ) : null}
      </button>
      {onResolve ? (
        <button
          type="button"
          onClick={(ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            onResolve(item.id);
          }}
          aria-label={`Resolve: ${item.title}`}
          className="absolute top-1.5 right-1.5 inline-flex h-5 w-5 items-center justify-center rounded-(--radius-stamp) bg-(--color-paper)/60 text-(--color-ink-3) hover:bg-(--color-paper-3) hover:text-(--color-ink)"
        >
          <Check className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

/** First non-empty line of the markdown body — used as a one-line
 *  preview in the row. The drawer renders the full markdown when
 *  the user clicks through. */
function firstLine(body: string): string {
  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (trimmed) return trimmed;
  }
  return "";
}

/** Small chip representing a single reference (issue / session /
 *  node / etc.). Click is handled by the parent row's button —
 *  chips are presentational here; navigation lives in the drawer. */
function ReferenceChip({
  reference,
}: {
  reference: import("@/lib/api/endpoints/inbox").InboxReference;
}) {
  const { kind, label } = describeReference(reference);
  return (
    <span className="inline-flex items-center gap-1 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-1.5 py-0.5 font-mono text-[10px] text-(--color-ink-3) tracking-[0.04em]">
      <span className="text-(--color-ink-3)/70">{kind}</span>
      <span className="text-(--color-ink)">{label}</span>
    </span>
  );
}

function describeReference(ref: import("@/lib/api/endpoints/inbox").InboxReference): {
  kind: string;
  label: string;
} {
  if ("issue" in ref) return { kind: "issue", label: ref.issue };
  if ("epic" in ref) return { kind: "epic", label: ref.epic };
  if ("session" in ref) return { kind: "session", label: ref.session };
  if ("node" in ref)
    return { kind: "node", label: ref.version ? `${ref.node} @ ${ref.version}` : ref.node };
  if ("artifact" in ref)
    return { kind: "artifact", label: `${ref.artifact.session}/${ref.artifact.file}` };
  if ("comment" in ref) return { kind: "comment", label: `${ref.comment.issue}#${ref.comment.id}` };
  if ("pr" in ref) return { kind: "pr", label: ref.pr };
  return { kind: "ref", label: "unknown" };
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-2 text-center font-serif text-[13px] italic text-(--color-ink-3)">
      {children}
    </div>
  );
}
