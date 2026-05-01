import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { TWEAK_DEFAULTS, TweaksProvider } from "@/components/tweaks/TweaksContext";
import { TweaksPanel } from "@/components/tweaks/TweaksPanel";

const STORAGE_KEY = "tripwire.tweaks.v1";

function wrap(ui: ReactNode, initialPath = "/") {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <TweaksProvider>{ui}</TweaksProvider>
    </MemoryRouter>
  );
}

describe("TweaksPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("style");
  });
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("does not render the panel by default", () => {
    render(wrap(<TweaksPanel />));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens when defaultOpen is true", () => {
    render(wrap(<TweaksPanel defaultOpen />));
    expect(screen.getByRole("dialog", { name: /tweaks/i })).toBeInTheDocument();
  });

  it("renders the six tweak dimensions when open", () => {
    render(wrap(<TweaksPanel defaultOpen />));
    expect(screen.getByLabelText(/paper warmth/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/rule colour/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/density/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/stamp shape/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/serif family/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/mono family/i)).toBeInTheDocument();
  });

  it("persists changed settings to localStorage under tripwire.tweaks.v1", async () => {
    const user = userEvent.setup();
    render(wrap(<TweaksPanel defaultOpen />));
    await user.selectOptions(screen.getByLabelText(/paper warmth/i), "linen");
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(stored.paperWarmth).toBe("linen");
  });

  it("loads stored settings on mount", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...TWEAK_DEFAULTS, ruleColour: "ochre" }));
    render(wrap(<TweaksPanel defaultOpen />));
    expect(screen.getByLabelText(/rule colour/i)).toHaveValue("ochre");
  });

  it("writes a CSS variable on the document root when the rule colour changes", async () => {
    const user = userEvent.setup();
    render(wrap(<TweaksPanel defaultOpen />));
    await user.selectOptions(screen.getByLabelText(/rule colour/i), "indigo");
    // The Tweaks panel pushes the chosen value into the CSS custom
    // property tree on <html>; CSS-only consumers (like the
    // LifecycleWire's `stroke="var(--color-rule)"`) pick it up
    // automatically without React re-renders.
    expect(document.documentElement.style.getPropertyValue("--color-rule")).not.toBe("");
  });

  // Per PM follow-up — exercise the alternative-pick path on every
  // dimension so the conditional render branches in TweaksPanel are
  // covered. Each select.options-change writes to localStorage and to
  // the CSS-var tree; we assert both effects in one shot per dimension.
  it.each([
    ["density", "loose", "--space-density"],
    ["stamp shape", "ticket-cut", "--radius-stamp"],
    ["serif family", "EB Garamond", "--font-serif"],
    ["mono family", "JetBrains Mono", "--font-mono"],
  ])("propagates a non-default %s pick to localStorage + CSS vars", async (label, choice, cssVar) => {
    const user = userEvent.setup();
    render(wrap(<TweaksPanel defaultOpen />));
    await user.selectOptions(screen.getByLabelText(new RegExp(label, "i")), choice);
    expect(document.documentElement.style.getPropertyValue(cssVar)).not.toBe("");
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    // Stored key uses camelCase; map label → key.
    const camel = label
      .split(" ")
      .map((part, i) => {
        if (i === 0) return part;
        const head = part[0] ?? "";
        return head.toUpperCase() + part.slice(1);
      })
      .join("");
    expect(stored[camel]).toBe(choice);
  });

  it("auto-opens when the URL has ?tweaks=1", () => {
    render(wrap(<TweaksPanel />, "/?tweaks=1"));
    expect(screen.getByRole("dialog", { name: /tweaks/i })).toBeInTheDocument();
  });

  it("closes when the close button is clicked", async () => {
    const user = userEvent.setup();
    render(wrap(<TweaksPanel defaultOpen />));
    await user.click(screen.getByRole("button", { name: /close tweaks/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens when the tripwire:tweaks-toggle window event fires", () => {
    render(wrap(<TweaksPanel />));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Wrap the dispatch in act() — the state update from the toggle
    // listener has to flush before the next assertion or the panel
    // hasn't re-rendered yet.
    act(() => {
      window.dispatchEvent(new CustomEvent("tripwire:tweaks-toggle"));
    });
    expect(screen.getByRole("dialog", { name: /tweaks/i })).toBeInTheDocument();
  });

  it("falls back to defaults when localStorage holds garbage JSON", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");
    render(wrap(<TweaksPanel defaultOpen />));
    // The defensive try/catch in loadFromStorage routes to TWEAK_DEFAULTS
    // — the cream/red/comfortable defaults render without crashing.
    expect(screen.getByLabelText(/paper warmth/i)).toHaveValue("cream");
    expect(screen.getByLabelText(/rule colour/i)).toHaveValue("red");
  });
});
