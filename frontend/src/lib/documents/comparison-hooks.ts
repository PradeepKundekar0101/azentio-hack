"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

export const comparisonKeys = {
  comparison: (claimId: string) => ["documents", "comparison", claimId] as const,
  extraction: (documentId: number, version: number) => ["documents", "extraction", documentId, version] as const,
};

export function useDocumentComparison(claimId: string) {
  return useQuery({
    queryKey: comparisonKeys.comparison(claimId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/claims/{claim_id}/document-comparison", { params: { path: { claim_id: claimId } } }),
      ),
  });
}

export function useExtraction(documentId: number, version: number) {
  return useQuery({
    queryKey: comparisonKeys.extraction(documentId, version),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents/{document_id}/extraction", {
          params: { path: { document_id: documentId }, query: { version } },
        }),
      ),
  });
}

/** Same-origin URL of a document's file (the session cookie goes with it). */
export function documentContentUrl(documentId: number): string {
  return `/api/v1/documents/${documentId}/content`;
}
