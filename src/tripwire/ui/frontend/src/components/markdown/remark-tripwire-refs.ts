import type { Link, PhrasingContent, Root, Text } from "mdast";
import type { Plugin } from "unified";
import { SKIP, visit } from "unist-util-visit";

export interface Reference {
  token: string;
  resolves_as?: "node" | "issue" | "session" | "dangling";
  is_stale?: boolean;
}

export interface RemarkTripwireRefsOptions {
  projectId: string;
  refs?: Reference[];
}

const REF_RE = /\[\[([a-z0-9][a-z0-9-]*|[A-Z][A-Z0-9]*-\d+)\]\]/g;
const ISSUE_KEY_RE = /^[A-Z][A-Z0-9]*-\d+$/;

const remarkTripwireRefs: Plugin<[RemarkTripwireRefsOptions], Root> = (options) => {
  const { projectId, refs } = options;
  const refMap = new Map(refs?.map((r) => [r.token, r]));

  return (tree) => {
    visit(tree, "text", (node: Text, index, parent) => {
      if (index === undefined || !parent) return;

      const matches = Array.from(node.value.matchAll(REF_RE));
      if (matches.length === 0) return;

      const children: PhrasingContent[] = [];
      let lastEnd = 0;

      for (const match of matches) {
        const start = match.index ?? 0;
        const token = match[1] ?? "";
        const fullMatch = match[0] ?? "";

        if (start > lastEnd) {
          children.push({ type: "text", value: node.value.slice(lastEnd, start) });
        }

        const ref = refMap.get(token);
        const isIssue = ISSUE_KEY_RE.test(token);

        // Prefer the backend's resolved kind when provided — issue keys and
        // node/session slugs can look identical to the regex, and only the
        // server knows whether a lowercase token is a node or a session.
        let segment: "issues" | "nodes" | "sessions";
        if (ref?.resolves_as === "session") {
          segment = "sessions";
        } else if (ref?.resolves_as === "issue" || isIssue) {
          segment = "issues";
        } else {
          segment = "nodes";
        }
        const href = `/p/${projectId}/${segment}/${token}`;

        const link: Link = {
          type: "link",
          url: href,
          children: [{ type: "text", value: token }],
        };

        if (ref?.resolves_as === "dangling" || ref?.is_stale) {
          const resolveStatus = ref.resolves_as === "dangling" ? "dangling" : "stale";
          link.data = {
            hProperties: { "data-resolves": resolveStatus },
          };
        }

        children.push(link);
        lastEnd = start + fullMatch.length;
      }

      if (lastEnd < node.value.length) {
        children.push({ type: "text", value: node.value.slice(lastEnd) });
      }

      parent.children.splice(index, 1, ...children);
      return [SKIP, index + children.length];
    });
  };
};

export default remarkTripwireRefs;
