import { ApiError } from "./client";

const UNREACHABLE = "We couldn't reach the server. Check your connection and try again.";

/** The API says "Expected available in 540 seconds"; people read minutes. */
function waitInMinutes(error: ApiError) {
  const seconds = Number(/(\d{1,6}) seconds/.exec(error.message)?.[1] ?? 60);
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

/** One sentence for a failed action, whatever went wrong. The API's own message is shown for the problems
 * it explains (validation, workflow rules, conflicts); never for server errors, whose text is internal. */
export function describeError(error: unknown): string {
  if (!(error instanceof ApiError) || error.code === "network") return UNREACHABLE;
  if (error.code === "timeout") return "The server took too long to answer. Try again in a moment.";
  if (error.status === 403) return "Your account isn't allowed to do this. Ask an administrator if you need it.";
  if (error.status === 429) return `Too many requests. Try again in ${waitInMinutes(error)}.`;
  if (error.status >= 500) return "Something went wrong on our side. Try again in a moment.";
  return error.message;
}

/** What to do after a failed load, by its cause. */
export function loadErrorHint(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) return "Your account doesn't have access to this.";
  if (error instanceof ApiError && error.status === 429) return describeError(error);
  if (error instanceof ApiError && error.status >= 500) return "The service had a problem. Try again in a moment.";
  if (error instanceof ApiError && error.code === "timeout") return describeError(error);
  return "Check your connection. If it keeps happening, the service may be down for a moment.";
}
