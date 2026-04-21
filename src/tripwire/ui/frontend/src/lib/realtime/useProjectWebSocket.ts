import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { dispatchEvent } from "./eventHandlers";
import type { TripwireUiEvent } from "./events";
import {
  createWebSocketClient,
  type WebSocketClient,
  type WebSocketClientStatus,
} from "./websocketClient";

export type UseProjectWebSocketStatus = WebSocketClientStatus;

interface TrackedConnection {
  client: WebSocketClient;
  refCount: number;
  status: UseProjectWebSocketStatus;
  statusListeners: Set<(status: UseProjectWebSocketStatus) => void>;
}

/**
 * Module-level registry keyed by project id. Survives Vite HMR because
 * module state is preserved across hot updates; without it, re-mounting
 * `ProjectLayout` during a dev reload would leak one socket per reload.
 */
const connections = new Map<string, TrackedConnection>();

/** Build the WebSocket URL. Exported for tests. */
export function buildWebSocketUrl(projectId: string): string {
  const explicit = import.meta.env.VITE_TRIPWIRE_WS_URL as string | undefined;
  if (explicit) {
    const joiner = explicit.includes("?") ? "&" : "?";
    return `${explicit}${joiner}project=${encodeURIComponent(projectId)}`;
  }
  const loc = typeof window !== "undefined" ? window.location : undefined;
  const scheme = loc?.protocol === "https:" ? "wss:" : "ws:";
  const host = loc?.host ?? "localhost:8000";
  return `${scheme}//${host}/api/ws?project=${encodeURIComponent(projectId)}`;
}

/**
 * Open (or attach to) a single WebSocket per project id and dispatch
 * events into the TanStack cache. Returns the current connection status
 * so the UI can render a dot.
 *
 * Re-mounts under the same project id share the connection via a
 * module-level ref count — the socket only closes when the last
 * consumer unmounts. That makes HMR and StrictMode double-invocation
 * safe.
 */
export function useProjectWebSocket(projectId: string): { status: UseProjectWebSocketStatus } {
  const queryClient = useQueryClient();
  const initial = connections.get(projectId)?.status ?? "connecting";
  const [status, setStatus] = useState<UseProjectWebSocketStatus>(initial);

  useEffect(() => {
    let tracked = connections.get(projectId);

    if (!tracked) {
      const entry: TrackedConnection = {
        client: null as unknown as WebSocketClient,
        refCount: 0,
        status: "connecting",
        statusListeners: new Set(),
      };
      entry.client = createWebSocketClient({
        url: buildWebSocketUrl(projectId),
        onEvent: (event: TripwireUiEvent) => {
          dispatchEvent(event, queryClient);
        },
        onStatusChange: (next) => {
          entry.status = next;
          for (const listener of entry.statusListeners) {
            listener(next);
          }
        },
      });
      connections.set(projectId, entry);
      tracked = entry;
    }

    tracked.refCount += 1;
    const listener = (next: UseProjectWebSocketStatus) => setStatus(next);
    tracked.statusListeners.add(listener);
    setStatus(tracked.status);

    return () => {
      const entry = connections.get(projectId);
      if (!entry) return;
      entry.statusListeners.delete(listener);
      entry.refCount -= 1;
      if (entry.refCount <= 0) {
        entry.client.close();
        connections.delete(projectId);
      }
    };
  }, [projectId, queryClient]);

  return { status };
}

/** Test/HMR escape hatch — tear down every live connection. */
export function __resetProjectWebSocketsForTests(): void {
  for (const entry of connections.values()) {
    entry.client.close();
  }
  connections.clear();
}
