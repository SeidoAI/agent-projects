import type { TripwireUiEvent } from "./events";

export type WebSocketClientStatus = "connecting" | "open" | "closed" | "error";

export interface WebSocketClientOptions {
  /** WebSocket URL, e.g. `ws://localhost:8000/api/ws?project=<pid>`. */
  url: string;
  /** Called for every parsed JSON event that arrived from the server. */
  onEvent: (event: TripwireUiEvent) => void;
  onOpen?: () => void;
  onClose?: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
  onStatusChange?: (status: WebSocketClientStatus) => void;
  /** Initial reconnect delay (default 250ms). */
  initialDelayMs?: number;
  /** Max reconnect delay (default 8000ms). */
  maxDelayMs?: number;
  /** Jitter fraction applied ±symmetrically (default 0.25 = ±25%). */
  jitter?: number;
  /** Override the native WebSocket constructor for tests. */
  createSocket?: (url: string) => WebSocket;
  /** Override the delay scheduler for tests. Returns a cancel function. */
  schedule?: (cb: () => void, delayMs: number) => () => void;
  /** Override the jitter RNG for tests. Returns a value in [0, 1). */
  random?: () => number;
}

export interface WebSocketClient {
  /** Tear down permanently — closes the socket and stops reconnecting. */
  close(): void;
  /** Current status; reflects the underlying socket state. */
  getStatus(): WebSocketClientStatus;
}

const DEFAULT_INITIAL_DELAY_MS = 250;
const DEFAULT_MAX_DELAY_MS = 8000;
const DEFAULT_JITTER = 0.25;

function defaultSchedule(cb: () => void, delayMs: number): () => void {
  const id = globalThis.setTimeout(cb, delayMs);
  return () => globalThis.clearTimeout(id);
}

function defaultCreateSocket(url: string): WebSocket {
  return new WebSocket(url);
}

/**
 * Create a reconnecting WebSocket client with backoff-with-jitter.
 *
 * Reconnect attempt N waits `min(maxDelay, initialDelay * 2**(N-1))`
 * multiplied by a uniform jitter factor in `[1 - jitter, 1 + jitter]`.
 * Explicit `close()` cancels any pending reconnect and halts the client.
 */
export function createWebSocketClient(options: WebSocketClientOptions): WebSocketClient {
  const initialDelay = options.initialDelayMs ?? DEFAULT_INITIAL_DELAY_MS;
  const maxDelay = options.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;
  const jitter = options.jitter ?? DEFAULT_JITTER;
  const schedule = options.schedule ?? defaultSchedule;
  const createSocket = options.createSocket ?? defaultCreateSocket;
  const random = options.random ?? Math.random;

  let socket: WebSocket | null = null;
  let status: WebSocketClientStatus = "connecting";
  let closed = false;
  let cancelReconnect: (() => void) | null = null;
  let attempts = 0;

  function setStatus(next: WebSocketClientStatus): void {
    if (status === next) return;
    status = next;
    options.onStatusChange?.(next);
  }

  function computeDelay(attempt: number): number {
    const exponent = Math.max(0, attempt - 1);
    const base = Math.min(maxDelay, initialDelay * 2 ** exponent);
    // random() in [0, 1) → factor in [1 - jitter, 1 + jitter).
    const factor = 1 - jitter + random() * 2 * jitter;
    return Math.max(0, Math.round(base * factor));
  }

  function connect(): void {
    if (closed) return;
    setStatus("connecting");

    const next = createSocket(options.url);
    socket = next;

    next.onopen = () => {
      if (closed) return;
      attempts = 0;
      setStatus("open");
      options.onOpen?.();
    };

    next.onmessage = (ev: MessageEvent) => {
      if (closed) return;
      let parsed: TripwireUiEvent;
      try {
        parsed = JSON.parse(typeof ev.data === "string" ? ev.data : String(ev.data));
      } catch {
        // Malformed payload — surface as an error but keep the socket open.
        options.onError?.(new Event("parse-error"));
        return;
      }
      options.onEvent(parsed);
    };

    next.onerror = (ev: Event) => {
      if (closed) return;
      setStatus("error");
      options.onError?.(ev);
      // Native `close` fires after `error` — reconnect logic lives there.
    };

    next.onclose = (ev: CloseEvent) => {
      options.onClose?.(ev);
      socket = null;
      if (closed) {
        setStatus("closed");
        return;
      }
      scheduleReconnect();
    };
  }

  function scheduleReconnect(): void {
    attempts += 1;
    const delay = computeDelay(attempts);
    setStatus("connecting");
    cancelReconnect = schedule(() => {
      cancelReconnect = null;
      connect();
    }, delay);
  }

  connect();

  return {
    close() {
      if (closed) return;
      closed = true;
      if (cancelReconnect) {
        cancelReconnect();
        cancelReconnect = null;
      }
      if (socket) {
        // Clear handlers before close to avoid a late `onclose` firing
        // reconnect logic (the `closed` flag already guards this, but
        // this also prevents spurious callbacks after teardown).
        const current = socket;
        current.onopen = null;
        current.onmessage = null;
        current.onerror = null;
        current.onclose = null;
        try {
          current.close();
        } catch {
          // Already closed — ignore.
        }
        socket = null;
      }
      setStatus("closed");
    },
    getStatus() {
      return status;
    },
  };
}
