import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TripwireUiEvent } from "@/lib/realtime/events";
import { createWebSocketClient } from "@/lib/realtime/websocketClient";

type MessageHandler = (ev: MessageEvent) => void;
type CloseHandler = (ev: CloseEvent) => void;
type ErrorHandler = (ev: Event) => void;
type OpenHandler = () => void;

interface FakeSocket {
  url: string;
  onopen: OpenHandler | null;
  onmessage: MessageHandler | null;
  onclose: CloseHandler | null;
  onerror: ErrorHandler | null;
  close: () => void;
  fireOpen(): void;
  fireMessage(data: unknown): void;
  fireError(ev?: Event): void;
  fireClose(ev?: CloseEvent): void;
}

interface PendingSchedule {
  cb: () => void;
  delayMs: number;
  cancelled: boolean;
}

function makeScheduler() {
  const pending: PendingSchedule[] = [];
  const schedule = (cb: () => void, delayMs: number) => {
    const entry: PendingSchedule = { cb, delayMs, cancelled: false };
    pending.push(entry);
    return () => {
      entry.cancelled = true;
    };
  };
  const runLast = () => {
    const entry = pending.at(-1);
    if (entry && !entry.cancelled) entry.cb();
  };
  return { schedule, pending, runLast };
}

function makeSocketFactory() {
  const sockets: FakeSocket[] = [];
  const createSocket = (url: string): WebSocket => {
    const socket: FakeSocket = {
      url,
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
      close: vi.fn(),
      fireOpen: () => socket.onopen?.(),
      fireMessage: (data: unknown) => {
        socket.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
      },
      fireError: (ev?: Event) => socket.onerror?.(ev ?? new Event("error")),
      fireClose: (ev?: CloseEvent) =>
        socket.onclose?.(ev ?? ({ code: 1006, reason: "", wasClean: false } as CloseEvent)),
    };
    sockets.push(socket);
    return socket as unknown as WebSocket;
  };
  return { createSocket, sockets };
}

describe("createWebSocketClient", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses JSON messages and forwards them to onEvent", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule } = makeScheduler();
    const onEvent = vi.fn();

    const client = createWebSocketClient({
      url: "ws://localhost/api/ws?project=p1",
      onEvent,
      createSocket,
      schedule,
      random: () => 0.5,
    });

    const socket = sockets[0];
    if (!socket) throw new Error("expected one socket created");
    socket.fireOpen();
    expect(client.getStatus()).toBe("open");

    const wireEvent: TripwireUiEvent = {
      type: "ping",
      timestamp: "2026-04-21T00:00:00.000Z",
    };
    socket.fireMessage(wireEvent);

    expect(onEvent).toHaveBeenCalledWith(wireEvent);
    client.close();
  });

  it("forwards onOpen / onClose / onError hooks", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule } = makeScheduler();
    const onOpen = vi.fn();
    const onClose = vi.fn();
    const onError = vi.fn();

    createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      onOpen,
      onClose,
      onError,
      createSocket,
      schedule,
      random: () => 0.5,
    });

    const socket = sockets[0];
    if (!socket) throw new Error("expected one socket created");
    socket.fireOpen();
    expect(onOpen).toHaveBeenCalledTimes(1);

    const err = new Event("error");
    socket.fireError(err);
    expect(onError).toHaveBeenCalledWith(err);

    const close = { code: 1006, reason: "", wasClean: false } as CloseEvent;
    socket.fireClose(close);
    expect(onClose).toHaveBeenCalledWith(close);
  });

  it("surfaces a parse error without closing the socket", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule } = makeScheduler();
    const onEvent = vi.fn();
    const onError = vi.fn();

    createWebSocketClient({
      url: "ws://x",
      onEvent,
      onError,
      createSocket,
      schedule,
      random: () => 0.5,
    });

    const socket = sockets[0];
    if (!socket) throw new Error("expected one socket created");
    socket.fireOpen();
    socket.onmessage?.({ data: "{not json" } as MessageEvent);

    expect(onEvent).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("reconnects with backoff-with-jitter and resets attempts on reopen", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule, pending, runLast } = makeScheduler();

    // random() = 0.5 → jitter factor = 1 → delay equals base.
    createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      initialDelayMs: 250,
      maxDelayMs: 8000,
      jitter: 0.25,
      random: () => 0.5,
      createSocket,
      schedule,
    });

    const socket1 = sockets[0];
    if (!socket1) throw new Error("expected socket 1");
    socket1.fireOpen();
    socket1.fireClose();
    expect(pending.at(-1)?.delayMs).toBe(250);

    runLast();
    const socket2 = sockets[1];
    if (!socket2) throw new Error("expected socket 2");
    socket2.fireClose(); // never opened — attempt 2
    expect(pending.at(-1)?.delayMs).toBe(500);

    runLast();
    const socket3 = sockets[2];
    if (!socket3) throw new Error("expected socket 3");
    socket3.fireClose();
    expect(pending.at(-1)?.delayMs).toBe(1000);

    // Reopen resets the attempt counter.
    runLast();
    const socket4 = sockets[3];
    if (!socket4) throw new Error("expected socket 4");
    socket4.fireOpen();
    socket4.fireClose();
    expect(pending.at(-1)?.delayMs).toBe(250);
  });

  it("caps the backoff at maxDelayMs", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule, pending, runLast } = makeScheduler();

    createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      initialDelayMs: 250,
      maxDelayMs: 8000,
      jitter: 0,
      random: () => 0.5,
      createSocket,
      schedule,
    });

    for (let i = 0; i < 8; i++) {
      const s = sockets[i];
      if (!s) throw new Error(`expected socket ${i}`);
      s.fireClose();
      if (i < 7) runLast();
    }

    expect(pending.at(-1)?.delayMs).toBe(8000);
  });

  it("applies ±jitter around the base delay", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule, pending } = makeScheduler();

    createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      initialDelayMs: 1000,
      jitter: 0.25,
      random: () => 0, // lower bound: factor = 0.75
      createSocket,
      schedule,
    });

    const s = sockets[0];
    if (!s) throw new Error("expected socket 0");
    s.fireClose();

    expect(pending.at(-1)?.delayMs).toBe(750);
  });

  it("close() cancels any pending reconnect", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule, pending } = makeScheduler();

    const client = createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      createSocket,
      schedule,
      random: () => 0.5,
    });

    const socket1 = sockets[0];
    if (!socket1) throw new Error("expected socket 1");
    socket1.fireClose();

    client.close();

    const last = pending.at(-1);
    expect(last?.cancelled).toBe(true);
    expect(client.getStatus()).toBe("closed");
    expect(sockets.length).toBe(1);
  });

  it("reports status transitions via onStatusChange", () => {
    const { createSocket, sockets } = makeSocketFactory();
    const { schedule } = makeScheduler();
    const onStatusChange = vi.fn();

    const client = createWebSocketClient({
      url: "ws://x",
      onEvent: vi.fn(),
      onStatusChange,
      createSocket,
      schedule,
      random: () => 0.5,
    });

    const socket = sockets[0];
    if (!socket) throw new Error("expected one socket");
    socket.fireOpen();
    socket.fireError();
    client.close();

    const statuses = onStatusChange.mock.calls.map((c) => c[0]);
    expect(statuses).toContain("open");
    expect(statuses).toContain("error");
    expect(statuses.at(-1)).toBe("closed");
  });
});
