import { Check, Copy } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import type { PluggableList } from "unified";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

import "highlight.js/styles/github-dark.css";

import type { Reference } from "./markdown/remark-tripwire-refs";
import remarkTripwireRefs from "./markdown/remark-tripwire-refs";
import { tripwireSanitizeSchema } from "./markdown/sanitize-schema";

export type { Reference } from "./markdown/remark-tripwire-refs";

interface MarkdownBodyProps {
  content: string;
  projectId: string;
  compact?: boolean;
  refs?: Reference[];
}

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard permission denied or insecure context
    }
  }, [code]);

  return (
    <Button
      variant="ghost"
      size="icon"
      className="absolute top-2 right-2 h-7 w-7 opacity-0 transition-opacity group-hover/code:opacity-100"
      onClick={handleCopy}
      aria-label="Copy code"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  );
}

export function MarkdownBody({ content, projectId, compact, refs }: MarkdownBodyProps) {
  const remarkPlugins = useMemo<PluggableList>(
    () => [remarkGfm, [remarkTripwireRefs, { projectId, refs }]],
    [projectId, refs],
  );
  const rehypePlugins = useMemo<PluggableList>(
    () => [rehypeHighlight, [rehypeSanitize, tripwireSanitizeSchema]],
    [],
  );

  return (
    // Cream-paper foundation (KUI-101) means we render dark ink on
    // light background. PM #25 round 2 P1 caught a leftover
    // `prose-invert` from the v0.7 dark-default era making body
    // text near-invisible on the graph rail; dropping it lets the
    // default Tailwind Typography ink tokens take effect across
    // every consumer (graph rail, session detail, etc.).
    <div
      className={cn(
        "prose max-w-none text-(--color-ink) prose-headings:text-(--color-ink) prose-strong:text-(--color-ink) prose-a:text-(--color-rule)",
        compact && "prose-sm",
      )}
    >
      <Markdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          a({ href, children, ...props }) {
            const resolves = (props as Record<string, unknown>)["data-resolves"] as
              | string
              | undefined;

            const resolveClass =
              resolves === "dangling"
                ? "underline decoration-red-500 decoration-wavy"
                : resolves === "stale"
                  ? "underline decoration-orange-400 decoration-wavy"
                  : undefined;

            if (href?.startsWith("/")) {
              return (
                <Link to={href} className={resolveClass} data-resolves={resolves}>
                  {children}
                </Link>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className={resolveClass}
                data-resolves={resolves}
              >
                {children}
              </a>
            );
          },
          pre({ children }) {
            return <pre className="group/code relative">{children}</pre>;
          },
          code({ children, className, ...rest }) {
            const isBlock = className?.startsWith("hljs");
            if (!isBlock) {
              return (
                <code className={className} {...rest}>
                  {children}
                </code>
              );
            }
            const codeText = extractText(children);
            return (
              <>
                <code className={className} {...rest}>
                  {children}
                </code>
                <CopyButton code={codeText} />
              </>
            );
          },
          table({ children }) {
            return <Table>{children}</Table>;
          },
          thead({ children }) {
            return <TableHeader>{children}</TableHeader>;
          },
          tbody({ children }) {
            return <TableBody>{children}</TableBody>;
          },
          tr({ children }) {
            return <TableRow>{children}</TableRow>;
          },
          th({ children }) {
            return <TableHead>{children}</TableHead>;
          },
          td({ children }) {
            return <TableCell>{children}</TableCell>;
          },
          input({ checked, disabled, ...rest }) {
            return (
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                readOnly
                className="mr-1.5 pointer-events-none"
                {...rest}
              />
            );
          },
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}

function extractText(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (!node) return "";
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    const props = (node as { props: { children?: React.ReactNode } }).props;
    return extractText(props.children);
  }
  return "";
}
