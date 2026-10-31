import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/**
 * Typed API client, generated from the backend's OpenAPI schema (`pnpm api:types`).
 *
 * The base URL is relative on purpose: Next.js rewrites `/api/*` and `/health` to the
 * FastAPI backend (see next.config.ts), so the `azentio_session` cookie is always
 * first-party. This client is meant for the browser; relative URLs do not resolve on the
 * server.
 */
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "include",
  headers: { Accept: "application/json" },
});

export type Schemas = components["schemas"];

/** Every list endpoint takes `page` and `page_size` and returns this shape. */
export interface Page<T> {
  items: T[];
  total: number;
}
