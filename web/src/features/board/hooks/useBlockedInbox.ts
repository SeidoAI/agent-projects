import { useMemo } from "react";

import { type InboxItem, useInbox } from "@/lib/api/endpoints/inbox";

/** Index of "session id / issue key → list of open BLOCKED inbox
 *  entries that reference it". Drives both the card cross-link badge
 *  ("↗ inbox" chip per amendment) and the `has-blocked-inbox-entry`
 *  filter pill (the replacement for the misframed `has-tripwires`
 *  pill — tripwires are agent-facing per
 *  `[[dec-tripwires-are-agent-facing]]`, blocked inbox entries are
 *  PM-facing per `[[dec-pm-only-inbox-authoring]]`).
 *
 *  Returns empty maps when the underlying query is loading or errors;
 *  callers read by id and treat absence as "no entries". */
export interface BlockedInboxIndex {
  /** Map session id → array of open BLOCKED inbox entries. */
  bySession: Map<string, InboxItem[]>;
  /** Map issue key → array of open BLOCKED inbox entries. */
  byIssue: Map<string, InboxItem[]>;
  /** True only after the underlying inbox query resolves. */
  ready: boolean;
}

const EMPTY: BlockedInboxIndex = {
  bySession: new Map(),
  byIssue: new Map(),
  ready: false,
};

export function useBlockedInbox(projectId: string): BlockedInboxIndex {
  const query = useInbox(projectId, { bucket: "blocked" });
  return useMemo(() => {
    if (!query.data) return EMPTY;
    const bySession = new Map<string, InboxItem[]>();
    const byIssue = new Map<string, InboxItem[]>();
    for (const item of query.data) {
      // Resolved entries no longer demand attention; the cross-link
      // badge would be visual noise.
      if (item.resolved) continue;
      for (const ref of item.references) {
        if ("session" in ref) {
          const arr = bySession.get(ref.session) ?? [];
          arr.push(item);
          bySession.set(ref.session, arr);
        } else if ("issue" in ref) {
          const arr = byIssue.get(ref.issue) ?? [];
          arr.push(item);
          byIssue.set(ref.issue, arr);
        }
      }
    }
    return { bySession, byIssue, ready: true };
  }, [query.data]);
}
