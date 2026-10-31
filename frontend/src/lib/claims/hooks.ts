"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

export const claimsKeys = {
  all: ["claims"] as const,
  detail: (id: string) => ["claims", "detail", id] as const,
};

export function useClaim(id: string) {
  return useQuery({
    queryKey: claimsKeys.detail(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/claims/{claim_id}", { params: { path: { claim_id: id } } })),
  });
}
