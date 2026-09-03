/**
 * Typed API client.
 *
 * - Base URL comes from configuration, never a literal.
 * - A 401 triggers exactly one refresh attempt; concurrent requests share it
 *   rather than each firing their own refresh.
 * - Errors surface as `ApiError` carrying the backend's human-readable message,
 *   so UI code never has to render a raw exception.
 */

import { config } from "./config";
import type { ApiErrorBody, LoginResponse } from "./types";

const ACCESS_KEY = "rs.access_token";
const REFRESH_KEY = "rs.refresh_token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when the failure looks like a lost connection rather than a rejection. */
  get isOffline(): boolean {
    return this.code === "network_unavailable";
  }
}

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(tokens: { access_token: string; refresh_token: string }): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Notified when the session can no longer be recovered. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

let refreshInFlight: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  const refreshToken = tokenStore.refresh;
  if (!refreshToken) return false;

  // Share a single refresh across concurrent 401s — refresh tokens rotate, so
  // parallel refreshes would invalidate one another and log the user out.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${config.apiBaseUrl}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        const data = (await response.json()) as LoginResponse;
        tokenStore.set(data.tokens);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Send FormData as-is (file uploads). */
  formData?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Skip the auth header (login/refresh). */
  anonymous?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${config.apiBaseUrl}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body?.error) {
      return new ApiError(response.status, body.error.code, body.error.message, body.error.details);
    }
  } catch {
    /* fall through to a generic message */
  }
  return new ApiError(
    response.status,
    "unexpected_error",
    "Something went wrong. Please try again.",
  );
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, query, signal, anonymous } = options;

  const send = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (!formData) headers["Content-Type"] = "application/json";
    if (!anonymous && tokenStore.access) {
      headers.Authorization = `Bearer ${tokenStore.access}`;
    }
    return fetch(buildUrl(path, query), {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    });
  };

  let response: Response;
  try {
    response = await send();
  } catch (error) {
    if ((error as Error)?.name === "AbortError") throw error;
    // Distinguish "no connection" from "server said no" — the offline UX
    // depends on this being explicit rather than a generic failure.
    throw new ApiError(
      0,
      "network_unavailable",
      "You appear to be offline. Your work is saved on this device.",
    );
  }

  if (response.status === 401 && !anonymous) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      response = await send();
    } else {
      tokenStore.clear();
      unauthorizedListeners.forEach((listener) => listener());
      throw new ApiError(401, "session_expired", "Your session has expired. Please sign in again.");
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"], signal?: AbortSignal) =>
    request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown, query?: RequestOptions["query"]) =>
    request<T>(path, { method: "POST", body, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  // Deletes answer 204 with no body; `request` already returns undefined there.
  del: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", formData }),
  anonymousPost: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body, anonymous: true }),
};
