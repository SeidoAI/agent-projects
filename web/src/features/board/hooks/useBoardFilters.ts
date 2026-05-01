import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/** Multi-select filter state for the Board screen. State lives in
 *  the URL query string so a board view is shareable / linkable —
 *  paste the URL, the recipient sees the same filter set.
 *
 *  Filter dimensions per `KUI-102/issue.yaml` AC, with
 *  `has-tripwires` replaced by `has-blocked-inbox-entry` per the
 *  v0.8.x amendment (`[[dec-tripwires-are-agent-facing]]`).
 *
 *  Each dimension is multi-value comma-separated EXCEPT the two
 *  boolean toggles (`has-blocked-inbox-entry`, `blocked`) which are
 *  encoded as the literal "1" when active.
 *
 *  The `view` param chooses between sessions and issues. Per spec
 *  §3.3 it must preserve filter state across switches — keeping it
 *  in the same URL achieves that for free. */
export type BoardView = "sessions" | "issues";

export interface BoardFilters {
  view: BoardView;
  agents: Set<string>;
  owners: Set<string>;
  ages: Set<string>;
  hasBlockedInbox: boolean;
  blocked: boolean;
}

export interface BoardFilterControls {
  filters: BoardFilters;
  setView: (view: BoardView) => void;
  toggleAgent: (agent: string) => void;
  toggleOwner: (owner: string) => void;
  toggleAge: (age: string) => void;
  toggleBlockedInbox: () => void;
  toggleBlocked: () => void;
  clearAll: () => void;
}

const PARAM_VIEW = "view";
const PARAM_AGENT = "agent";
const PARAM_OWNER = "owner";
const PARAM_AGE = "age";
const PARAM_BLOCKED_INBOX = "inbox";
const PARAM_BLOCKED = "blocked";

function readSet(params: URLSearchParams, key: string): Set<string> {
  const raw = params.get(key);
  if (!raw) return new Set();
  return new Set(raw.split(",").filter(Boolean));
}

function writeSet(params: URLSearchParams, key: string, set: Set<string>) {
  if (set.size === 0) {
    params.delete(key);
  } else {
    params.set(key, [...set].sort().join(","));
  }
}

function readView(params: URLSearchParams): BoardView {
  const raw = params.get(PARAM_VIEW);
  return raw === "issues" ? "issues" : "sessions";
}

export function useBoardFilters(): BoardFilterControls {
  const [params, setParams] = useSearchParams();

  const filters = useMemo<BoardFilters>(
    () => ({
      view: readView(params),
      agents: readSet(params, PARAM_AGENT),
      owners: readSet(params, PARAM_OWNER),
      ages: readSet(params, PARAM_AGE),
      hasBlockedInbox: params.get(PARAM_BLOCKED_INBOX) === "1",
      blocked: params.get(PARAM_BLOCKED) === "1",
    }),
    [params],
  );

  const update = useCallback(
    (mut: (next: URLSearchParams) => void) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          mut(next);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const setView = useCallback(
    (view: BoardView) => {
      update((next) => {
        if (view === "sessions") next.delete(PARAM_VIEW);
        else next.set(PARAM_VIEW, view);
      });
    },
    [update],
  );

  const toggleIn = useCallback(
    (key: string, value: string) => {
      update((next) => {
        const current = readSet(next, key);
        if (current.has(value)) current.delete(value);
        else current.add(value);
        writeSet(next, key, current);
      });
    },
    [update],
  );

  const toggleAgent = useCallback((a: string) => toggleIn(PARAM_AGENT, a), [toggleIn]);
  const toggleOwner = useCallback((o: string) => toggleIn(PARAM_OWNER, o), [toggleIn]);
  const toggleAge = useCallback((a: string) => toggleIn(PARAM_AGE, a), [toggleIn]);

  const toggleBool = useCallback(
    (key: string) => {
      update((next) => {
        if (next.get(key) === "1") next.delete(key);
        else next.set(key, "1");
      });
    },
    [update],
  );

  const toggleBlockedInbox = useCallback(() => toggleBool(PARAM_BLOCKED_INBOX), [toggleBool]);
  const toggleBlocked = useCallback(() => toggleBool(PARAM_BLOCKED), [toggleBool]);

  const clearAll = useCallback(() => {
    update((next) => {
      next.delete(PARAM_AGENT);
      next.delete(PARAM_OWNER);
      next.delete(PARAM_AGE);
      next.delete(PARAM_BLOCKED_INBOX);
      next.delete(PARAM_BLOCKED);
    });
  }, [update]);

  return {
    filters,
    setView,
    toggleAgent,
    toggleOwner,
    toggleAge,
    toggleBlockedInbox,
    toggleBlocked,
    clearAll,
  };
}

/** Bucket a card creation date into a coarse age band, used by the
 *  `age` filter pill. Buckets match what the dashboard's stage row
 *  surfaces — same vocabulary across screens. */
export function ageBucket(createdAt: string | null): string {
  if (!createdAt) return "unknown";
  const ms = Date.now() - Date.parse(createdAt);
  const days = ms / (1000 * 60 * 60 * 24);
  if (days < 1) return "today";
  if (days < 7) return "this-week";
  if (days < 30) return "this-month";
  return "older";
}
