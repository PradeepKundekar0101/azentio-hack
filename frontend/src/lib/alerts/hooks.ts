"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

import { type AlertFilters, type AlertSort, filtersToApiQuery } from "./filters";
import type {
  AlertDetail,
  AlertStatus,
  EscalationTarget,
} from "@/lib/alerts/model";

export const alertsKeys = {
  all: ["alerts"] as const,
  list: (filters: AlertFilters, sort: AlertSort, page: number, pageSize: number) =>
    ["alerts", "list", filters, sort, page, pageSize] as const,
  detail: (id: number) => ["alerts", "detail", id] as const,
  cleared: (page: number, pageSize: number) => ["alerts", "cleared", page, pageSize] as const,
  summary: (filters: AlertFilters) => ["dashboard", "summary", filters] as const,
  escalations: ["alerts", "escalations"] as const,
};

/** Escalated alerts waiting for the signed-in user's level, and the ones they escalated. Polls, so the
 *  sidebar count works as a notification. */
export function useEscalations() {
  return useQuery({
    queryKey: alertsKeys.escalations,
    queryFn: async () => unwrap(await api.GET("/api/v1/alerts/escalations")),
    refetchInterval: 15_000,
  });
}

export function useAlerts(filters: AlertFilters, sort: AlertSort, page: number, pageSize: number) {
  return useQuery({
    queryKey: alertsKeys.list(filters, sort, page, pageSize),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/alerts", {
          params: { query: { ...filtersToApiQuery(filters), sort, page, page_size: pageSize } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAlert(id: number) {
  return useQuery({
    queryKey: alertsKeys.detail(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/alerts/{alert_id}", { params: { path: { alert_id: id } } })),
  });
}

export function useClearedDuplicates(page: number, pageSize: number, enabled = true) {
  return useQuery({
    queryKey: alertsKeys.cleared(page, pageSize),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/duplicates/cleared", { params: { query: { page, page_size: pageSize } } })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useDashboardSummary(filters: AlertFilters) {
  return useQuery({
    queryKey: alertsKeys.summary(filters),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/dashboard/summary", { params: { query: filtersToApiQuery(filters) } })),
    placeholderData: keepPreviousData,
  });
}

/** Every provider, for the filter and for naming providers in filter chips. */
export function useProviders() {
  return useQuery({
    queryKey: ["reference", "providers"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/reference/providers", { params: { query: { page: 1, page_size: 200 } } })),
    staleTime: 10 * 60_000,
  });
}

export interface AlertReview {
  status: AlertStatus;
  note: string | null;
  escalate_to?: EscalationTarget | null;
}

/** Records a decision on an alert (confirm, false positive, request evidence, escalate, reopen);
 * lists and the dashboard refresh after. */
export function useReviewAlert(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (review: AlertReview) =>
      unwrap(
        await api.PATCH("/api/v1/alerts/{alert_id}", {
          params: { path: { alert_id: id } },
          body: { status: review.status, note: review.note, escalate_to: review.escalate_to ?? null },
        }),
      ),
    onSuccess: (alert) => {
      queryClient.setQueryData<AlertDetail>(alertsKeys.detail(id), (old) => (old ? { ...old, alert } : old));
      void queryClient.invalidateQueries({ queryKey: ["alerts", "list"] });
      void queryClient.invalidateQueries({ queryKey: alertsKeys.escalations });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["claims"] });
    },
  });
}
