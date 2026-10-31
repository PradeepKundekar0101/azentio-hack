"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type Schemas } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";

export type Health = Schemas["HealthOut"];

function isHealth(body: unknown): body is Health {
  return !!body && typeof body === "object" && "status" in body && "checks" in body;
}

/** `GET /health`. A 503 still carries the per-service checks, so it is data, not an error. */
async function fetchHealth(): Promise<Health> {
  const { data, error, response } = await api.GET("/health");
  if (data) return data;
  const body: unknown = error;
  if (response.status === 503 && isHealth(body)) return body;
  throw toApiError(body, response);
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
  });
}

/** Names of the services that failed their check ("database", "storage"). */
export function failedChecks(health: Health): string[] {
  return Object.entries(health.checks)
    .filter(([, result]) => result !== "ok")
    .map(([name]) => name);
}
