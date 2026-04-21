export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
    public extras?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }

  isV2NotImplemented(): boolean {
    return this.status === 501 && this.code === "v2/not_implemented";
  }
}

interface RequestOptions {
  signal?: AbortSignal;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 204) {
    return undefined as T;
  }
  if (res.ok) {
    return res.json() as Promise<T>;
  }
  let body: { detail?: string; code?: string; extras?: Record<string, unknown> } = {};
  try {
    body = await res.json();
  } catch {
    // non-JSON error body — fall through with empty body
  }
  throw new ApiError(
    res.status,
    body.code ?? null,
    body.detail ?? `HTTP ${res.status}`,
    body.extras,
  );
}

export async function apiGet<T>(path: string, opts?: RequestOptions): Promise<T> {
  const res = await fetch(path, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal: opts?.signal,
  });
  return handleResponse<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: opts?.signal,
  });
  return handleResponse<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown, opts?: RequestOptions): Promise<T> {
  const res = await fetch(path, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts?.signal,
  });
  return handleResponse<T>(res);
}

export async function apiDelete<T>(path: string, opts?: RequestOptions): Promise<T> {
  const res = await fetch(path, {
    method: "DELETE",
    headers: { Accept: "application/json" },
    signal: opts?.signal,
  });
  return handleResponse<T>(res);
}
