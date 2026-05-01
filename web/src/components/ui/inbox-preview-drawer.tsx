import { Check, X } from "lucide-react";

import { MarkdownBody } from "@/components/MarkdownBody";
import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { Stamp } from "@/components/ui/stamp";
import { type InboxItem, useInboxItem, useResolveInbox } from "@/lib/api/endpoints/inbox";

/**
 * Side-sliding drawer that previews a single inbox entry —
 * triggered when a row in the AttentionQueue is clicked.
 *
 * Renders the full markdown body, references chip strip, and an
 * embedded resolve button so the PM can act without opening a
 * separate detail screen. Content fetched lazily (only when
 * ``open=true``) via ``useInboxItem``.
 *
 * Outer chrome (overlay, slide-in panel, close button, header /
 * footer bands) lives in :class:`EntityPreviewDrawer` so the same
 * shape is shared across inbox / session / issue previews per
 * `[[dec-shared-preview-drawer]]`. This module owns just the
 * inbox-specific body + footer renderer.
 */
export interface InboxPreviewDrawerProps {
  projectId: string;
  /** Entry id to preview, or null/undefined when closed. */
  entryId: string | null;
  onClose: () => void;
  /** Optional pre-loaded item (e.g. demo data). When provided
   *  the drawer skips the network fetch and renders this directly. */
  prefetchedItem?: InboxItem | null;
}

export function InboxPreviewDrawer({
  projectId,
  entryId,
  onClose,
  prefetchedItem,
}: InboxPreviewDrawerProps) {
  const open = entryId !== null;
  // Skip the fetch when we already have the item in hand (demo
  // mode). The query always runs to keep hook order stable but
  // its result is overridden when ``prefetchedItem`` is provided.
  const fetched = useInboxItem(projectId, entryId ?? "");
  const item = prefetchedItem ?? (entryId ? fetched.data : null) ?? null;
  const isLoading = !prefetchedItem && entryId !== null && fetched.isLoading;
  const isError = !prefetchedItem && entryId !== null && fetched.isError;

  const resolveMutation = useResolveInbox(projectId);
  const handleResolve = () => {
    if (!entryId) return;
    resolveMutation.mutate(
      { id: entryId },
      {
        onSuccess: () => onClose(),
      },
    );
  };

  if (item) {
    return (
      <EntityPreviewDrawer
        open={open}
        onClose={onClose}
        title={item.title}
        headerSlot={<InboxHeaderRow item={item} isDemo={Boolean(prefetchedItem)} />}
        body={<InboxBody item={item} projectId={projectId} />}
        footerSlot={
          <InboxFooter
            item={item}
            isDemo={Boolean(prefetchedItem)}
            onResolve={handleResolve}
            resolving={resolveMutation.isPending}
          />
        }
      />
    );
  }
  if (isLoading) {
    return (
      <EntityPreviewDrawer open={open} onClose={onClose} title="loading…" body={<LoadingBody />} />
    );
  }
  if (isError) {
    return (
      <EntityPreviewDrawer
        open={open}
        onClose={onClose}
        title="entry not found"
        body={<ErrorBody />}
      />
    );
  }
  return null;
}

function LoadingBody() {
  return <p className="font-serif text-[13px] italic text-(--color-ink-3)">loading…</p>;
}

function ErrorBody() {
  return (
    <p className="font-mono text-[11px] text-(--color-rule) uppercase tracking-[0.18em]">
      entry not found
    </p>
  );
}

function InboxHeaderRow({ item, isDemo }: { item: InboxItem; isDemo: boolean }) {
  const isBlocked = item.bucket === "blocked";
  const created = new Date(item.created_at);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Stamp tone={isBlocked ? "rule" : "default"} variant="status">
        {item.bucket}
      </Stamp>
      <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        {item.author} · {created.toISOString().slice(0, 16).replace("T", " ")}
      </span>
      {isDemo ? (
        <Stamp tone="info" variant="identifier">
          demo
        </Stamp>
      ) : null}
    </div>
  );
}

function InboxBody({ item, projectId }: { item: InboxItem; projectId: string }) {
  return (
    <>
      {item.body.trim() ? (
        <MarkdownBody content={item.body} projectId={projectId} compact={false} />
      ) : (
        <p className="font-serif text-[14px] italic text-(--color-ink-3)">
          (no body — title-only entry)
        </p>
      )}
      {item.references.length > 0 ? (
        <div className="mt-6">
          <div className="mb-2 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            references
          </div>
          <ul className="flex flex-col gap-1.5">
            {item.references.map((ref, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: refs have no stable id
              <li key={i}>
                <ReferenceRow reference={ref} projectId={projectId} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {item.escalation_reason ? (
        <div className="mt-6 font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
          escalation reason · {item.escalation_reason}
        </div>
      ) : null}
    </>
  );
}

function InboxFooter({
  item,
  isDemo,
  onResolve,
  resolving,
}: {
  item: InboxItem;
  isDemo: boolean;
  onResolve: () => void;
  resolving: boolean;
}) {
  const isBlocked = item.bucket === "blocked";
  return (
    <>
      {item.resolved ? (
        <span className="font-mono text-[11px] text-(--color-ink-3) tracking-[0.06em]">
          resolved · {item.resolved_by ?? "—"}
        </span>
      ) : (
        <span className="font-mono text-[11px] text-(--color-ink-3) tracking-[0.06em]">
          {isBlocked ? "needs your decision" : "informational"}
        </span>
      )}
      {item.resolved || isDemo ? null : (
        <button
          type="button"
          onClick={onResolve}
          disabled={resolving}
          className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule) px-3 py-1.5 font-mono text-[11px] text-(--color-paper) uppercase tracking-[0.18em] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" aria-hidden />
          {resolving ? "resolving…" : "resolve"}
        </button>
      )}
    </>
  );
}

/** Test-friendly renderer that mounts the inbox drawer body without
 *  going through the Radix Dialog portal (jsdom doesn't render the
 *  portal + animations reliably). Composes the same slot helpers
 *  the production drawer uses, so test coverage of the inbox-specific
 *  bits — header row, body, footer, references — also covers the
 *  shipped drawer one indirection level up. */
export function InboxDrawerContents({
  item,
  projectId,
  onClose,
  onResolve,
  resolving,
  isDemo,
}: {
  item: InboxItem;
  /** Threaded through so MarkdownBody and ReferenceRow build
   *  project-scoped hrefs (`/p/<projectId>/issues/...`). Empty
   *  string is allowed for previews outside a project context but
   *  produces root-relative links — pass the real id whenever
   *  available. */
  projectId: string;
  onClose: () => void;
  onResolve: () => void;
  resolving: boolean;
  isDemo: boolean;
}) {
  return (
    <>
      <header className="flex items-start justify-between gap-3 border-(--color-edge) border-b px-5 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2">
            <InboxHeaderRow item={item} isDemo={isDemo} />
          </div>
          <h2 className="m-0 font-sans font-semibold text-[20px] text-(--color-ink) leading-tight tracking-[-0.01em]">
            {item.title}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close preview"
          className="inline-flex h-7 w-7 items-center justify-center rounded-(--radius-stamp) text-(--color-ink-3) hover:bg-(--color-paper-3) hover:text-(--color-ink)"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <InboxBody item={item} projectId={projectId} />
      </div>
      <footer className="flex items-center justify-between gap-3 border-(--color-edge) border-t bg-(--color-paper-2) px-5 py-3">
        <InboxFooter item={item} isDemo={isDemo} onResolve={onResolve} resolving={resolving} />
      </footer>
    </>
  );
}

function ReferenceRow({
  reference,
  projectId,
}: {
  reference: import("@/lib/api/endpoints/inbox").InboxReference;
  projectId: string;
}) {
  const { kind, label, href } = describeReferenceDeep(reference, projectId);
  const inner = (
    <span className="inline-flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1.5 font-mono text-[11px] text-(--color-ink-2)">
      <span className="text-(--color-ink-3) uppercase tracking-[0.06em]">{kind}</span>
      <span className="text-(--color-ink)">{label}</span>
    </span>
  );
  if (href) {
    return (
      <a href={href} className="inline-block transition-colors hover:opacity-80">
        {inner}
      </a>
    );
  }
  return inner;
}

function describeReferenceDeep(
  ref: import("@/lib/api/endpoints/inbox").InboxReference,
  projectId: string,
): { kind: string; label: string; href: string | null } {
  const projectPath = projectId ? `/p/${projectId}` : "";
  if ("issue" in ref) {
    return { kind: "issue", label: ref.issue, href: `${projectPath}/issues/${ref.issue}` };
  }
  if ("epic" in ref) {
    return { kind: "epic", label: ref.epic, href: `${projectPath}/issues/${ref.epic}` };
  }
  if ("session" in ref) {
    return {
      kind: "session",
      label: ref.session,
      href: `${projectPath}/sessions/${ref.session}`,
    };
  }
  if ("node" in ref) {
    return {
      kind: "node",
      label: ref.version ? `${ref.node} @ ${ref.version}` : ref.node,
      href: `${projectPath}/graph#${ref.node}`,
    };
  }
  if ("artifact" in ref) {
    return {
      kind: "artifact",
      label: `${ref.artifact.session}/${ref.artifact.file}`,
      href: `${projectPath}/sessions/${ref.artifact.session}`,
    };
  }
  if ("comment" in ref) {
    return {
      kind: "comment",
      label: `${ref.comment.issue}#${ref.comment.id}`,
      href: `${projectPath}/issues/${ref.comment.issue}`,
    };
  }
  if ("pr" in ref) {
    return { kind: "pr", label: ref.pr, href: `https://github.com/${ref.pr}` };
  }
  return { kind: "ref", label: "unknown", href: null };
}
