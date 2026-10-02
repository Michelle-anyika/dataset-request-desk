import { http, HttpResponse } from "msw";

import type { DatasetRequest, User } from "../api/types";

export const client: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "client-a@example.com",
  full_name: "Carla Client",
  role: "client",
  organisation: "Acme Robotics",
};
export const operator: User = {
  id: "22222222-2222-4222-8222-222222222222",
  email: "ops1@example.com",
  full_name: "Olu Operator",
  role: "operator",
  organisation: "",
};
export const admin: User = { ...operator, id: "33333333-3333-4333-8333-333333333333", role: "admin", full_name: "Ada Admin" };

export const apiError = (status: number, code: string, message: string, details?: unknown) =>
  HttpResponse.json({ error: { code, message, details } }, { status });

/** A browser with no session: the refresh cookie is missing or expired. */
export const noSession = () => http.post("/api/auth/refresh/", () => apiError(401, "not_authenticated", "No active session."));

/** A browser whose refresh cookie is still valid for `user` (e.g. after a page reload). */
export const sessionFor = (user: User) => [
  http.post("/api/auth/refresh/", () => HttpResponse.json({ access: `access-for-${user.role}` })),
  http.get("/api/auth/me/", () => HttpResponse.json(user)),
];

export function makeRequest(overrides: Partial<DatasetRequest> = {}): DatasetRequest {
  return {
    id: "aaaaaaaa-0000-4000-8000-000000000001",
    client: { id: client.id, full_name: client.full_name, organisation: client.organisation },
    task_name: "pick cup",
    episodes_requested: 20,
    assigned_count: 0,
    deadline: "2026-12-01",
    notes: "",
    status: "submitted",
    status_changed_at: "2026-10-01T09:00:00Z",
    created_at: "2026-10-01T09:00:00Z",
    ...overrides,
  };
}

export function page<T>(results: T[], count = results.length) {
  return { count, next: null, previous: null, results };
}
