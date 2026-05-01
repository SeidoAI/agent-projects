import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InboxDrawerContents } from "@/components/ui/inbox-preview-drawer";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { renderWithProviders } from "../test-utils";

function makeItem(overrides: Partial<InboxItem> = {}): InboxItem {
  return {
    id: "inb-1",
    bucket: "blocked",
    title: "test entry",
    body: "Body line one.\nBody line two.",
    author: "pm-agent",
    created_at: "2026-04-27T10:00:00Z",
    references: [],
    escalation_reason: null,
    resolved: false,
    resolved_at: null,
    resolved_by: null,
    ...overrides,
  };
}

function renderContents(props: Parameters<typeof InboxDrawerContents>[0]) {
  return renderWithProviders(<InboxDrawerContents {...props} />);
}

const noop = () => {};

describe("InboxDrawerContents", () => {
  afterEach(() => cleanup());

  it("renders the bucket label and the markdown body", () => {
    renderContents({
      item: makeItem({
        bucket: "fyi",
        title: "session merged",
        body: "Cost: $42 · validator clean",
      }),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: false,
    });
    expect(screen.getByText("session merged")).toBeInTheDocument();
    // The bucket label appears as a status stamp in the header.
    expect(screen.getAllByText(/fyi/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Cost: \$42/)).toBeInTheDocument();
  });

  it("renders the demo badge when isDemo is true", () => {
    renderContents({
      item: makeItem({ title: "demo-only entry" }),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: true,
    });
    expect(screen.getByText("demo-only entry")).toBeInTheDocument();
    expect(screen.getByText(/^demo$/i)).toBeInTheDocument();
  });

  it("hides the resolve button for demo items", () => {
    // Demo items have no backend representation — resolving them
    // would 404. The button is hidden so the user doesn't try.
    renderContents({
      item: makeItem(),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: true,
    });
    expect(screen.queryByRole("button", { name: /^resolve$/i })).not.toBeInTheDocument();
  });

  it("hides the resolve button when the item is already resolved", () => {
    renderContents({
      item: makeItem({ resolved: true, resolved_by: "alice" }),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: false,
    });
    expect(screen.queryByRole("button", { name: /^resolve$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/resolved · alice/i)).toBeInTheDocument();
  });

  it("calls onClose when the X button is clicked", () => {
    const onClose = vi.fn();
    renderContents({
      item: makeItem(),
      projectId: "test-pid",
      onClose,
      onResolve: noop,
      resolving: false,
      isDemo: false,
    });
    fireEvent.click(screen.getByLabelText(/close preview/i));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onResolve when the resolve button is clicked", () => {
    const onResolve = vi.fn();
    renderContents({
      item: makeItem(),
      projectId: "test-pid",
      onClose: noop,
      onResolve,
      resolving: false,
      isDemo: false,
    });
    fireEvent.click(screen.getByRole("button", { name: /^resolve$/i }));
    expect(onResolve).toHaveBeenCalled();
  });

  it("disables the resolve button while a resolve is in flight", () => {
    renderContents({
      item: makeItem(),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: true,
      isDemo: false,
    });
    const btn = screen.getByRole("button", { name: /resolving…/i });
    expect(btn).toBeDisabled();
  });

  it("renders reference rows with deep-link hrefs", () => {
    renderContents({
      item: makeItem({
        references: [
          { issue: "SEI-42" },
          { node: "auth-token-endpoint", version: "v3" },
          { pr: "SeidoAI/tripwire/88" },
        ],
      }),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: false,
    });
    // Pinned-version nodes show "<id> @ <version>".
    expect(screen.getByText(/auth-token-endpoint @ v3/)).toBeInTheDocument();
    // PR refs link to GitHub absolute URL.
    expect(screen.getByText("SeidoAI/tripwire/88").closest("a")).toHaveAttribute(
      "href",
      "https://github.com/SeidoAI/tripwire/88",
    );
    // Project-scoped refs use /p/<projectId>/... — without the
    // threaded id these would resolve to root paths and break in
    // any project that's not at the URL root.
    expect(screen.getByText("SEI-42").closest("a")).toHaveAttribute(
      "href",
      "/p/test-pid/issues/SEI-42",
    );
    expect(screen.getByText(/auth-token-endpoint @ v3/).closest("a")).toHaveAttribute(
      "href",
      "/p/test-pid/graph#auth-token-endpoint",
    );
  });

  it("shows a placeholder when the body is empty", () => {
    renderContents({
      item: makeItem({ body: "" }),
      projectId: "test-pid",
      onClose: noop,
      onResolve: noop,
      resolving: false,
      isDemo: false,
    });
    expect(screen.getByText(/no body — title-only entry/i)).toBeInTheDocument();
  });
});
