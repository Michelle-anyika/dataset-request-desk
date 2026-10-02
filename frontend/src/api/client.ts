import type { AccessToken, ApiErrorBody } from "./types";

/** An error response from the API, in its one error shape. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field errors from a 400, e.g. `{ "deadline": ["..."] }`, ready for a form. */
  fieldErrors(): Record<string, string> {
    if (!this.details || typeof this.details !== "object") return {};
    return Object.fromEntries(
      Object.entries(this.details as Record<string, unknown>).map(([field, messages]) => [
        field,
        Array.isArray(messages) ? messages.join(" ") : String(messages),
      ]),
    );
  }
}

// The access token lives only in this module's memory: never in localStorage, where any script could read
// it (NOTES.md §4). A page reload loses it; the HttpOnly refresh cookie gets a new one.
let accessToken: string | null = null;
let onSessionExpired: () => void = () => {};

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function hasAccessToken() {
  return accessToken !== null;
}

/** Called when the session can't be refreshed any more, e.g. to send the user to the login page. */
export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler;
}

type Query = Record<string, string | number | boolean | string[] | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  headers?: Record<string, string>;
  /** Public auth endpoints: no bearer token, and a 401 is an answer, not a reason to refresh. */
  anonymous?: boolean;
  /** Give up after this long. Uploads get longer: a 20 MB export takes a while on a slow connection. */
  timeoutMs?: number;
}

const TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 120_000;

export function buildUrl(path: string, query?: Query) {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === "") continue; // the API refuses blank parameters
    for (const item of Array.isArray(value) ? value : [value]) params.append(name, String(item));
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body; // the browser sets the multipart boundary
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (!options.anonymous && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const timeout = AbortSignal.timeout(options.timeoutMs ?? (body instanceof FormData ? UPLOAD_TIMEOUT_MS : TIMEOUT_MS));
  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      credentials: "same-origin",
      signal: timeout,
    });
  } catch {
    // No HTTP answer at all: no answer in time, or offline, DNS, a dropped connection.
    if (timeout.aborted) throw new ApiError(0, "timeout", "The server took too long to answer.");
    throw new ApiError(0, "network", "We couldn't reach the server.");
  }
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const { error } = (await response.json()) as ApiErrorBody;
    return new ApiError(response.status, error.code, error.message, error.details);
  } catch {
    return new ApiError(response.status, "unexpected_response", "Something went wrong. Please try again.");
  }
}

// One refresh at a time: when several requests get a 401 together, they all wait for the same refresh.
let refreshing: Promise<boolean> | null = null;

/** Exchange the refresh cookie for a new access token. Resolves false when there is no valid session. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const response = await send("/api/auth/refresh/", { method: "POST", anonymous: true });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      setAccessToken(((await response.json()) as AccessToken).access);
      return true;
    } catch {
      return false; // network error: keep the current state, the next request will try again
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** Call the API. On a 401 it refreshes the session once and retries; if that fails, the session is over. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);
  if (response.status === 401 && !options.anonymous) {
    if (await refreshSession()) {
      response = await send(path, options);
    }
    if (response.status === 401) {
      onSessionExpired();
    }
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
