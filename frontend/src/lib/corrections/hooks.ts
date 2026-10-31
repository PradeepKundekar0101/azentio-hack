"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { ApiError, unwrap } from "@/lib/api/errors";

export const correctionKeys = {
  set: (claimId: string, version: number | null) => ["corrections", claimId, version] as const,
  versions: (claimId: string) => ["corrections", claimId, "versions"] as const,
};

export function useCorrections(claimId: string, version: number | null) {
  return useQuery({
    queryKey: correctionKeys.set(claimId, version),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/claims/{claim_id}/corrections", {
          params: { path: { claim_id: claimId }, query: version ? { version } : {} },
        }),
      ),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
}

export function useCorrectionVersions(claimId: string) {
  return useQuery({
    queryKey: correctionKeys.versions(claimId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/claims/{claim_id}/corrections/versions", { params: { path: { claim_id: claimId } } })),
  });
}

export function useRecompute(claimId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/claims/{claim_id}/corrections/recompute", { params: { path: { claim_id: claimId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["corrections", claimId] }),
  });
}
