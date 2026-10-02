// Names for the API's types, generated from the backend's OpenAPI schema (npm run api:types).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["User"];
export type Role = User["role"];
export type LoginResponse = Schemas["LoginResponse"];
export type AccessToken = Schemas["AccessToken"];

export type DatasetRequest = Schemas["DatasetRequest"];
export type NewDatasetRequest = Schemas["DatasetRequestRequest"];
export type RequestStatus = Schemas["RequestStatus"];
export type RequestEvent = Schemas["RequestEvent"];
export type AssignedEpisode = Schemas["AssignedEpisode"];
/** Staff also see who assigned and released; clients get only the episode and when it was assigned. */
export type Assignment = Pick<Schemas["AssignmentHistory"], "episode" | "assigned_at"> &
  Partial<Omit<Schemas["AssignmentHistory"], "episode" | "assigned_at">>;

export interface Page<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

/** Every API error has this shape (backend: apps/core/exceptions.py). */
export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
