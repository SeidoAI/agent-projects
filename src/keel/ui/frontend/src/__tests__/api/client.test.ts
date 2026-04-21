import { describe, expect, it, vi } from "vitest";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api/client";

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const res = {
    ok: response.ok ?? true,
    status: response.status ?? 200,
    json: response.json ?? (() => Promise.resolve({})),
  } as Response;
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(res);
}

describe("API client", () => {
  it("apiGet returns typed JSON on 200", async () => {
    const spy = mockFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "proj-1", name: "My Project" }),
    });
    const result = await apiGet<{ id: string; name: string }>("/api/projects/proj-1");
    expect(result).toEqual({ id: "proj-1", name: "My Project" });
    expect(spy).toHaveBeenCalledWith(
      "/api/projects/proj-1",
      expect.objectContaining({ method: "GET" }),
    );
    spy.mockRestore();
  });

  it("apiPost sends JSON body", async () => {
    const spy = mockFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ok: true }),
    });
    await apiPost("/api/things", { name: "test" });
    expect(spy).toHaveBeenCalledWith(
      "/api/things",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "test" }),
      }),
    );
    spy.mockRestore();
  });

  it("apiPatch sends PATCH request", async () => {
    const spy = mockFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ updated: true }),
    });
    const result = await apiPatch<{ updated: boolean }>("/api/things/1", { name: "new" });
    expect(result).toEqual({ updated: true });
    expect(spy).toHaveBeenCalledWith("/api/things/1", expect.objectContaining({ method: "PATCH" }));
    spy.mockRestore();
  });

  it("apiDelete sends DELETE request", async () => {
    const spy = mockFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ deleted: true }),
    });
    const result = await apiDelete<{ deleted: boolean }>("/api/things/1");
    expect(result).toEqual({ deleted: true });
    expect(spy).toHaveBeenCalledWith(
      "/api/things/1",
      expect.objectContaining({ method: "DELETE" }),
    );
    spy.mockRestore();
  });

  it("returns undefined for 204 No Content", async () => {
    const spy = mockFetch({ ok: true, status: 204 });
    const result = await apiDelete<void>("/api/things/1");
    expect(result).toBeUndefined();
    spy.mockRestore();
  });

  it("throws ApiError with JSON error body", async () => {
    const spy = mockFetch({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "Not found", code: "not_found" }),
    });
    await expect(apiGet("/api/missing")).rejects.toThrow(ApiError);
    try {
      await apiGet("/api/missing");
    } catch (e) {
      const err = e as ApiError;
      expect(err.status).toBe(404);
      expect(err.code).toBe("not_found");
      expect(err.message).toBe("Not found");
    }
    spy.mockRestore();
  });

  it("throws ApiError with fallback message for non-JSON error body", async () => {
    const spy = mockFetch({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });
    try {
      await apiGet("/api/broken");
    } catch (e) {
      const err = e as ApiError;
      expect(err.status).toBe(500);
      expect(err.code).toBeNull();
      expect(err.message).toBe("HTTP 500");
    }
    spy.mockRestore();
  });

  it("identifies v2 not-implemented errors", async () => {
    const spy = mockFetch({
      ok: false,
      status: 501,
      json: () =>
        Promise.resolve({ detail: "v2 feature not implemented", code: "v2/not_implemented" }),
    });
    try {
      await apiGet("/api/v2/agents");
    } catch (e) {
      const err = e as ApiError;
      expect(err.isV2NotImplemented()).toBe(true);
    }
    spy.mockRestore();
  });

  it("non-v2 501 is not identified as v2", async () => {
    const spy = mockFetch({
      ok: false,
      status: 501,
      json: () => Promise.resolve({ detail: "Not implemented", code: "generic" }),
    });
    try {
      await apiGet("/api/something");
    } catch (e) {
      const err = e as ApiError;
      expect(err.isV2NotImplemented()).toBe(false);
    }
    spy.mockRestore();
  });

  it("propagates network errors as raw Error", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiGet("/api/offline")).rejects.toThrow(TypeError);
    spy.mockRestore();
  });

  it("propagates AbortSignal cancellation", async () => {
    const controller = new AbortController();
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));
    controller.abort();
    await expect(apiGet("/api/slow", { signal: controller.signal })).rejects.toThrow(DOMException);
    spy.mockRestore();
  });
});
