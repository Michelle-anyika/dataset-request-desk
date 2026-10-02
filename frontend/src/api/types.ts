// Names for the API's types, generated from the backend's OpenAPI schema (npm run api:types).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["User"];
export type Role = User["role"];
export type LoginResponse = Schemas["LoginResponse"];
export type AccessToken = Schemas["AccessToken"];

/** Every API error has this shape (backend: apps/core/exceptions.py). */
export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
