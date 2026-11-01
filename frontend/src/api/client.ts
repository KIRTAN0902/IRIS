/**
 * Typed API client — the ONLY place that talks to the backend.
 * Components never call fetch directly; they use hooks built on this layer.
 *
 * Error contract: the backend returns {"error": {"code", "message"}} on
 * failure. Non-2xx responses throw ApiError carrying that parsed envelope.
 */

import type { ErrorEnvelope } from "@/types/api";

const isCapacitor = typeof window !== "undefined" && Boolean((window as unknown as { Capacitor?: unknown }).Capacitor);
const DEFAULT_API_BASE = isCapacitor ? "https://irisai.runs-on.dev/api" : "/api";
const BASE = import.meta.env.VITE_API_URL?.replace(/\/+$/, "") || DEFAULT_API_BASE;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly category: string;
  readonly retryable: boolean;
  readonly recoveryAction?: string;
  readonly requestId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    options: { category?: string; retryable?: boolean; recoveryAction?: string | null; requestId?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.category = options.category ?? "request";
    this.retryable = options.retryable ?? false;
    this.recoveryAction = options.recoveryAction ?? undefined;
    this.requestId = options.requestId;
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
  opts: {
    query?: Record<string, QueryValue>;
    body?: unknown;
    /** Send this Blob as-is (e.g. recorded audio) instead of a JSON body. */
    blob?: Blob;
    /** Return the response body as a Blob (e.g. audio) instead of JSON. */
    asBlob?: boolean;
    /** Return the raw Response so its body can be read as a stream. */
    asStream?: boolean;
    /** Per-request deadline; defaults to 90 seconds for AI/provider-backed routes. */
    timeoutMs?: number;
  } = {},
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs ?? 90_000;
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const json = opts.body !== undefined;
    response = await fetch(buildUrl(path, opts.query), {
      method,
      headers: opts.blob
        ? { "Content-Type": opts.blob.type || "application/octet-stream" }
        : json
          ? { "Content-Type": "application/json" }
          : undefined,
      body: opts.blob ?? (json ? JSON.stringify(opts.body) : undefined),
      signal: controller.signal,
    });
  } catch {
    globalThis.clearTimeout(timeoutId);
    // Network-level failure (backend down, DNS, CORS).
    if (controller.signal.aborted) {
      throw new ApiError(0, "TIMEOUT", "The request timed out.", {
        category: "timeout",
        retryable: true,
        recoveryAction: "Check the connection and retry. If this changed data, check its status first.",
      });
    }
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the IRIS backend.", {
      category: "network",
      retryable: true,
      recoveryAction: "Check the connection and retry.",
    });
  }

  try {
    if (response.status === 204) return undefined as T;
    if (opts.asBlob && response.ok) return (await response.blob()) as T;
    if (opts.asStream && response.ok) return response as T;

    let data: unknown = null;
    try {
      data = await response.json();
    } catch {
      if (controller.signal.aborted) throw new Error("request aborted while reading the response");
      // fallthrough: empty or non-JSON body
    }

    if (!response.ok) {
      const envelope = data as Partial<ErrorEnvelope> | null;
      const err = envelope?.error;
      throw new ApiError(
        response.status,
        err?.code ?? `HTTP_${response.status}`,
        err?.message ?? "The request failed.",
        {
          category: err?.category,
          retryable: err?.retryable,
          recoveryAction: err?.recovery_action,
          requestId: err?.correlation_id ?? response.headers.get("X-Request-ID") ?? undefined,
        },
      );
    }
    return data as T;
  } catch (cause) {
    if (controller.signal.aborted && !(cause instanceof ApiError)) {
      throw new ApiError(0, "TIMEOUT", "The request timed out.", {
        category: "timeout",
        retryable: true,
        recoveryAction: "Check the connection and retry. If this changed data, check its status first.",
      });
    }
    throw cause;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: Record<string, QueryValue>) =>
    request<T>("POST", path, { body, query }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
  /** POST a raw Blob (e.g. audio) and parse the JSON reply. */
  postBlob: <T>(path: string, blob: Blob) => request<T>("POST", path, { blob }),
  /** POST JSON and receive a Blob (e.g. audio). */
  postForBlob: (path: string, body: unknown) => request<Blob>("POST", path, { body, asBlob: true }),
  /** POST JSON and receive the raw Response, to read a streamed body as it arrives. */
  postForStream: (path: string, body: unknown) => request<Response>("POST", path, { body, asStream: true }),
};
