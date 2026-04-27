import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { renderWithProviders } from "../test-utils";

afterEach(() => cleanup());

describe("EntityPreviewDrawer", () => {
  it("renders the title and body when open", () => {
    renderWithProviders(
      <EntityPreviewDrawer
        open
        onClose={() => {}}
        title="some entity"
        body={<p>body content here</p>}
      />,
    );
    expect(screen.getByText("some entity")).toBeInTheDocument();
    expect(screen.getByText("body content here")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    renderWithProviders(
      <EntityPreviewDrawer
        open={false}
        onClose={() => {}}
        title="some entity"
        body={<p>body content here</p>}
      />,
    );
    expect(screen.queryByText("body content here")).not.toBeInTheDocument();
  });

  it("calls onClose when the close button is pressed", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <EntityPreviewDrawer
        open
        onClose={onClose}
        title="some entity"
        body={<p>body</p>}
      />,
    );
    fireEvent.click(screen.getByLabelText(/close preview/i));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders the optional header slot above the title", () => {
    renderWithProviders(
      <EntityPreviewDrawer
        open
        onClose={() => {}}
        title="some entity"
        body={<p>body</p>}
        headerSlot={<span data-testid="hdr-slot">badges go here</span>}
      />,
    );
    expect(screen.getByTestId("hdr-slot")).toBeInTheDocument();
  });

  it("renders the optional footer slot at the bottom", () => {
    renderWithProviders(
      <EntityPreviewDrawer
        open
        onClose={() => {}}
        title="some entity"
        body={<p>body</p>}
        footerSlot={<button type="button">act</button>}
      />,
    );
    expect(screen.getByRole("button", { name: /act/i })).toBeInTheDocument();
  });
});
