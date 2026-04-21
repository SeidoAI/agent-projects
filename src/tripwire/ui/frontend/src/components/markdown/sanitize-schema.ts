import type { Schema } from "hast-util-sanitize";
import { defaultSchema } from "rehype-sanitize";

/**
 * Extends rehype-sanitize's default schema for tripwire's markdown rendering.
 *
 * The default schema already handles:
 * - GFM tables, task lists, strikethrough, del
 * - javascript: URL blocking (only http/https/mailto/etc allowed on href)
 * - script tag stripping
 * - Blocking iframe, object, embed, form (not in tagNames allowlist)
 *
 * We extend it to allow:
 * - highlight.js class names on code and span (rehype-highlight output)
 * - data-resolves attribute on links (remark-tripwire-refs output)
 *
 * SECURITY REVIEW REQUIRED when adding new attributes, tags, or protocols here.
 * This schema is the second-to-last line of defence against XSS in rendered
 * markdown (the last being the browser itself). Widening the allowlist is not
 * a routine change — every new entry must be justified with the full threat
 * model in mind: attacker-controlled markdown should never be able to exfil
 * data, execute script, or smuggle event handlers through this schema.
 *
 * Note on property casing: hast property names for `data-*` attributes are
 * preserved as kebab-case (not camelCased) by mdast-util-to-hast when set via
 * `hProperties`. Schema entries MUST match the exact casing the pipeline
 * produces — camelCase entries silently miss. Verify with an end-to-end test
 * when in doubt.
 */
export const tripwireSanitizeSchema: Schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), ["data-resolves", "stale", "dangling"]],
    code: ["className"],
    span: ["className"],
  },
};
