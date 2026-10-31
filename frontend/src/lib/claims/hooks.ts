"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

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

export type ClaimStatusFilter = "open" | "settled" | "all";
export type ClaimReviewFilter = "clean" | "flagged" | "not_validated" | "all";
export type ClaimSort = "-incident_date" | "incident_date" | "-requested_amount" | "-leakage" | "claim_id";

export interface ClaimListQuery {
  status: ClaimStatusFilter;
  review: ClaimReviewFilter;
  q: string;
  sort: ClaimSort;
  page: number;
  pageSize: number;
}

export function useClaims({ status, review, q, sort, page, pageSize }: ClaimListQuery) {
  return useQuery({
    queryKey: [...claimsKeys.all, "list", status, review, q, sort, page, pageSize] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/claims", {
          params: { query: { status, review, q: q || undefined, sort, page, page_size: pageSize } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
