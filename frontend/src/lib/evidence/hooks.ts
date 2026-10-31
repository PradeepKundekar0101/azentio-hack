"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { Investigation } from "@/lib/evidence/model";

export const evidenceKeys = {
  all: ["evidence"] as const,
  list: (page: number, pageSize: number) => ["evidence", "list", page, pageSize] as const,
  claim: (claimId: string) => ["evidence", "claim", claimId] as const,
};

/** Evidence changes whenever anyone acts on the claim, so it is always refetched on open. */
export function useInvestigation(claimId: string) {
  return useQuery({
    queryKey: evidenceKeys.claim(claimId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/evidence/claims/{claim_id}", { params: { path: { claim_id: claimId } } })),
    staleTime: 0,
    refetchOnMount: "always",
  });
}

export function useInvestigations(page: number, pageSize: number) {
  return useQuery({
    queryKey: evidenceKeys.list(page, pageSize),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/evidence", { params: { query: { page, page_size: pageSize } } })),
    placeholderData: keepPreviousData,
    staleTime: 0,
    refetchOnMount: "always",
  });
}

function useStore(claimId: string) {
  const queryClient = useQueryClient();
  return (investigation: Investigation) => {
    queryClient.setQueryData(evidenceKeys.claim(claimId), investigation);
    void queryClient.invalidateQueries({ queryKey: ["evidence", "list"] });
  };
}

export function useOpenInvestigation(claimId: string) {
  const store = useStore(claimId);
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/evidence/claims/{claim_id}/open", { params: { path: { claim_id: claimId } } }),
      ),
    onSuccess: store,
  });
}

export interface OverrideInput {
  alertId: number;
  correction: string;
  reason: string;
}

export function useOverrideCorrection(claimId: string) {
  const store = useStore(claimId);
  return useMutation({
    mutationFn: async ({ alertId, correction, reason }: OverrideInput) =>
      unwrap(
        await api.POST("/api/v1/evidence/claims/{claim_id}/overrides", {
          params: { path: { claim_id: claimId } },
          body: { alert_id: alertId, correction, reason },
        }),
      ),
    onSuccess: store,
  });
}

export function useAddNote(claimId: string) {
  const store = useStore(claimId);
  return useMutation({
    mutationFn: async ({ text, alertId }: { text: string; alertId: number | null }) =>
      unwrap(
        await api.POST("/api/v1/evidence/claims/{claim_id}/notes", {
          params: { path: { claim_id: claimId } },
          body: { text, alert_id: alertId },
        }),
      ),
    onSuccess: store,
  });
}
