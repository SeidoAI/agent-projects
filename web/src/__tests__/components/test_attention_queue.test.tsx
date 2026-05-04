import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AttentionQueue } from "@/components/ui/attention-queue";
import type { InboxItem, InboxReference } from "@/lib/api/endpoints/inbox";

function blocked(id: string, title: string, body = "", refs: InboxReference[] = []): InboxItem {
  return item(id, "blocked", title, body, refs);
}

function fyi(id: string, title: string, body = "", refs: InboxReference[] = []): InboxItem {
  return item(id, "fyi", title, body, refs);
}

function item(
  id: string,
  bucket: "blocked" | "fyi",
  title: string,
  body: string,
  refs: InboxReference[],
): InboxItem {
  return {
    id,
    bucket,
    title,
    body,
    author: "pm-agent",
    created_at: "2026-04-27T10:00:00Z",
    references: refs,
    escalation_reason: null,
    resolved: false,
    resolved_at: null,
    resolved_by: null,
  };
}

function renderQueue(props: Parameters<typeof AttentionQueue>[0]) {
  return render(
    <MemoryRouter>
      <AttentionQueue {...props} />
    </MemoryRouter>,
  );
}

describe("AttentionQueue", () => {
  afterEach(() => cleanup());

  it("renders both panel labels with the right counts", () => {
    renderQueue({
      items: [blocked("b1", "blocker one"), blocked("b2", "blocker two"), fyi("f1", "fyi one")],
    });
    expect(screen.getByText(/needs you \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/happened \(1\)/)).toBeInTheDocument();
  });

  it("shows a reassuring empty state in the BLOCKED panel", () => {
    renderQueue({ items: [fyi("f1", "fyi only")] });
    expect(screen.getByText(/nothing blocking you right now/i)).toBeInTheDocument();
  });

  it("shows a placeholder in the FYI panel when empty", () => {
    renderQueue({ items: [blocked("b1", "blocker only")] });
    expect(screen.getByText(/no recent decisions/i)).toBeInTheDocument();
  });

  it("hides resolved items from both panels", () => {
    renderQueue({
      items: [{ ...blocked("b1", "stale alert"), resolved: true }, fyi("f1", "still here")],
    });
    expect(screen.queryByText("stale alert")).not.toBeInTheDocument();
    expect(screen.getByText("still here")).toBeInTheDocument();
  });

  it("collapses the FYI panel when the chevron is clicked", () => {
    renderQueue({ items: [fyi("f1", "fyi item")] });
    expect(screen.getByText("fyi item")).toBeInTheDocument();
    const fyiHeader = screen.getByRole("button", { expanded: true });
    fireEvent.click(fyiHeader);
    expect(screen.queryByText("fyi item")).not.toBeInTheDocument();
  });

  it("fires onResolve with the item id when the ✓ is clicked", () => {
    const onResolve = vi.fn();
    renderQueue({
      items: [blocked("b1", "needs decision")],
      onResolve,
    });
    fireEvent.click(screen.getByLabelText(/Resolve: needs decision/));
    expect(onResolve).toHaveBeenCalledWith("b1");
  });

  it("fires onSelectItem when the row body is clicked", () => {
    const onSelectItem = vi.fn();
    renderQueue({
      items: [blocked("b1", "click me")],
      onSelectItem,
    });
    // The row's title button (not the resolve ✓) carries the row click.
    const rowButton = screen.getByText("click me").closest("button");
    if (!rowButton) throw new Error("missing attention queue row button");
    fireEvent.click(rowButton);
    expect(onSelectItem).toHaveBeenCalledWith("b1");
  });

  it("renders one chip per reference under the row body", () => {
    renderQueue({
      items: [
        blocked("b1", "with refs", "body", [
          { issue: "SEI-42" },
          { node: "auth-token-endpoint", version: "v3" },
          { session: "storage-impl" },
        ]),
      ],
    });
    expect(screen.getByText("SEI-42")).toBeInTheDocument();
    // Pinned-version nodes show "<id> @ <version>" in the chip.
    expect(screen.getByText(/auth-token-endpoint @ v3/)).toBeInTheDocument();
    expect(screen.getByText("storage-impl")).toBeInTheDocument();
  });

  it("uses the first non-empty body line as the row preview", () => {
    // Multi-line markdown body — only the first line should appear in
    // the row; the drawer renders the full body when clicked.
    renderQueue({
      items: [blocked("b1", "title", "\n\nfirst real line\nsecond line\n")],
    });
    expect(screen.getByText("first real line")).toBeInTheDocument();
    expect(screen.queryByText("second line")).not.toBeInTheDocument();
  });
});
