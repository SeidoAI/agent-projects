import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Reference } from "@/components/MarkdownBody";
import { MarkdownBody } from "@/components/MarkdownBody";

function renderMarkdown(
  content: string,
  opts: { projectId?: string; compact?: boolean; refs?: Reference[] } = {},
) {
  const { projectId = "test-project", compact, refs } = opts;
  return render(
    <MemoryRouter>
      <MarkdownBody content={content} projectId={projectId} compact={compact} refs={refs} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("MarkdownBody", () => {
  describe("contrast on cream paper (PM #25 round 2 P1)", () => {
    it("does not apply prose-invert (which renders white text on cream)", () => {
      // Regression: prose-invert renders body copy in a near-white
      // text colour designed for dark backgrounds. The graph rail
      // (cream paper) made body text effectively invisible. Fix is
      // to drop prose-invert from the wrapper so the default
      // ink-on-light prose tokens take effect.
      const { container } = renderMarkdown("Body text on cream.");
      const wrapper = container.querySelector(".prose");
      expect(wrapper).not.toBeNull();
      expect(wrapper?.className ?? "").not.toMatch(/prose-invert\b/);
    });
  });

  describe("basic rendering", () => {
    it("renders headings", () => {
      renderMarkdown("# Hello\n\n## World");
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Hello");
      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("World");
    });

    it("renders paragraphs", () => {
      renderMarkdown("Some paragraph text.");
      expect(screen.getByText("Some paragraph text.")).toBeInTheDocument();
    });

    it("renders unordered lists", () => {
      renderMarkdown("- item one\n- item two");
      expect(screen.getByText("item one")).toBeInTheDocument();
      expect(screen.getByText("item two")).toBeInTheDocument();
    });

    it("renders inline code", () => {
      renderMarkdown("Use `foo()` here.");
      const code = screen.getByText("foo()");
      expect(code.tagName).toBe("CODE");
    });
  });

  describe("double-bracket refs", () => {
    it("renders node refs as links", () => {
      renderMarkdown("See [[some-node]] for details.");
      const link = screen.getByRole("link", { name: "some-node" });
      expect(link).toHaveAttribute("href", "/p/test-project/nodes/some-node");
    });

    it("renders issue key refs as links", () => {
      renderMarkdown("Fixed in [[KUI-58]].");
      const link = screen.getByRole("link", { name: "KUI-58" });
      expect(link).toHaveAttribute("href", "/p/test-project/issues/KUI-58");
    });

    it("renders multiple refs in one line", () => {
      renderMarkdown("See [[node-a]] and [[KUI-1]].");
      expect(screen.getByRole("link", { name: "node-a" })).toHaveAttribute(
        "href",
        "/p/test-project/nodes/node-a",
      );
      expect(screen.getByRole("link", { name: "KUI-1" })).toHaveAttribute(
        "href",
        "/p/test-project/issues/KUI-1",
      );
    });

    it("routes session refs to /sessions/ when the backend resolves them", () => {
      // The regex can't tell a session slug from a node slug — the backend
      // tells us via resolves_as. Without this routing, session refs 404.
      const refs: Reference[] = [{ token: "static-bundling", resolves_as: "session" }];
      renderMarkdown("See [[static-bundling]].", { refs });
      expect(screen.getByRole("link", { name: "static-bundling" })).toHaveAttribute(
        "href",
        "/p/test-project/sessions/static-bundling",
      );
    });

    it("routes to /nodes/ when no backend ref is supplied", () => {
      renderMarkdown("See [[some-slug]].");
      expect(screen.getByRole("link", { name: "some-slug" })).toHaveAttribute(
        "href",
        "/p/test-project/nodes/some-slug",
      );
    });

    it("leaves unmatched tokens as plain text", () => {
      renderMarkdown("See [[invalid token]] here.");
      expect(screen.queryByRole("link", { name: "invalid token" })).toBeNull();
      expect(screen.getByText(/invalid token/)).toBeInTheDocument();
    });

    it("leaves literal double brackets with spaces as text", () => {
      renderMarkdown("This [[has spaces]] stays literal.");
      expect(screen.queryAllByRole("link")).toHaveLength(0);
    });
  });

  describe("ref resolve status", () => {
    it("marks dangling refs with data-resolves attribute", () => {
      const refs: Reference[] = [{ token: "missing-node", resolves_as: "dangling" }];
      renderMarkdown("See [[missing-node]].", { refs });
      const link = screen.getByRole("link", { name: "missing-node" });
      expect(link).toHaveAttribute("data-resolves", "dangling");
    });

    it("marks stale refs with data-resolves attribute", () => {
      const refs: Reference[] = [{ token: "old-node", is_stale: true }];
      renderMarkdown("See [[old-node]].", { refs });
      const link = screen.getByRole("link", { name: "old-node" });
      expect(link).toHaveAttribute("data-resolves", "stale");
    });

    it("prefers dangling over stale when both flags are set", () => {
      const refs: Reference[] = [{ token: "both-node", resolves_as: "dangling", is_stale: true }];
      renderMarkdown("See [[both-node]].", { refs });
      const link = screen.getByRole("link", { name: "both-node" });
      expect(link).toHaveAttribute("data-resolves", "dangling");
    });
  });

  describe("sanitisation", () => {
    it("strips script tags", () => {
      const { container } = renderMarkdown('Hello <script>alert("xss")</script> world');
      expect(container.querySelector("script")).toBeNull();
      expect(container.textContent).toContain("Hello");
    });

    it("strips javascript: URLs from links", () => {
      const { container } = renderMarkdown('[click me](javascript:alert("xss"))');
      const anchor = container.querySelector("a");
      expect(anchor).toBeInTheDocument();
      expect(anchor?.getAttribute("href")).toBeNull();
    });

    it("strips iframe elements", () => {
      const { container } = renderMarkdown('<iframe src="https://evil.com"></iframe>');
      expect(container.querySelector("iframe")).toBeNull();
    });

    it("strips inline event handlers", () => {
      const { container } = renderMarkdown('<div onmouseover="alert(1)">hover</div>');
      const div = container.querySelector("div");
      expect(div?.getAttribute("onmouseover")).toBeNull();
    });
  });

  describe("links", () => {
    it("renders internal links with react-router Link", () => {
      renderMarkdown("[go here](/p/test/board)");
      const link = screen.getByRole("link", { name: "go here" });
      expect(link).toHaveAttribute("href", "/p/test/board");
      expect(link).not.toHaveAttribute("target");
    });

    it("renders external links with target=_blank and rel=noopener", () => {
      renderMarkdown("[example](https://example.com)");
      const link = screen.getByRole("link", { name: "example" });
      expect(link).toHaveAttribute("href", "https://example.com");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });
  });

  describe("compact mode", () => {
    it("adds prose-sm class when compact is true", () => {
      const { container } = renderMarkdown("Hello", { compact: true });
      const wrapper = container.firstElementChild;
      expect(wrapper?.classList.contains("prose-sm")).toBe(true);
    });

    it("does not add prose-sm when compact is false", () => {
      const { container } = renderMarkdown("Hello", { compact: false });
      const wrapper = container.firstElementChild;
      expect(wrapper?.classList.contains("prose-sm")).toBe(false);
    });
  });

  describe("code blocks", () => {
    it("renders a copy button on code blocks", () => {
      renderMarkdown("```js\nconsole.log('hi')\n```");
      expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    });

    it("copies code text to clipboard on click", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText },
      });

      renderMarkdown("```js\nhello\n```");
      fireEvent.click(screen.getByRole("button", { name: "Copy code" }));

      await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
      expect(writeText.mock.calls[0]?.[0]).toContain("hello");
    });

    it("handles clipboard write rejection gracefully", async () => {
      const writeText = vi.fn().mockRejectedValue(new Error("denied"));
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText },
      });
      const unhandledHandler = vi.fn();
      window.addEventListener("unhandledrejection", unhandledHandler);

      renderMarkdown("```js\nhello\n```");
      fireEvent.click(screen.getByRole("button", { name: "Copy code" }));

      await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
      // Give the microtask queue a chance to settle an unhandled rejection.
      await new Promise((r) => setTimeout(r, 0));
      window.removeEventListener("unhandledrejection", unhandledHandler);

      expect(unhandledHandler).not.toHaveBeenCalled();
    });
  });

  describe("GFM tables", () => {
    it("renders tables with proper structure", () => {
      const md = "| A | B |\n|---|---|\n| 1 | 2 |";
      renderMarkdown(md);
      expect(screen.getByText("A")).toBeInTheDocument();
      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
  });

  describe("task lists", () => {
    it("renders task list checkboxes", () => {
      renderMarkdown("- [x] done\n- [ ] not done");
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(2);
      expect(checkboxes[0]).toBeChecked();
      expect(checkboxes[1]).not.toBeChecked();
    });
  });
});
