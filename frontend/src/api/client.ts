/**
 * Typed API client — the ONLY place that talks to the backend.
 * Components never call fetch directly; they use hooks built on this layer.
 *
 * Error contract: the backend returns {"error": {"code", "message"}} on
 * failure. Non-2xx responses throw ApiError carrying that parsed envelope.
 */

import type { ErrorEnvelope } from "@/types/api";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  opts: { query?: Record<string, QueryValue>; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, opts.query), {
      method,
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    // Network-level failure (backend down, DNS, CORS).
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the IRIS backend.");
  }

  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // fallthrough: empty or non-JSON body
  }

  if (!response.ok) {
    const envelope = data as Partial<ErrorEnvelope> | null;
    const err = envelope?.error;
    throw new ApiError(
      response.status,
      err?.code ?? `HTTP_${response.status}`,
      err?.message ?? "The request failed.",
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: Record<string, QueryValue>) =>
    request<T>("POST", path, { body, query }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
