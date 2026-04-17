import type { Schema } from "hast-util-sanitize";
import { defaultSchema } from "rehype-sanitize";

/**
 * Extends rehype-sanitize's default schema for keel's markdown rendering.
 *
 * The default schema already handles:
 * - GFM tables, task lists, strikethrough, del
 * - javascript: URL blocking (only http/https/mailto/etc allowed on href)
 * - script tag stripping
 * - Blocking iframe, object, embed, form (not in tagNames allowlist)
 *
 * We extend it to allow:
 * - highlight.js class names on code and span (rehype-highlight output)
 * - data-resolves attribute on links (remark-keel-refs output)
 */
export const keelSanitizeSchema: Schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), ["data-resolves", "stale", "dangling"]],
    code: ["className"],
    span: ["className"],
  },
};
