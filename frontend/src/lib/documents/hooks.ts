"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { ApiError, toApiError, unwrap } from "@/lib/api/errors";

import type { ConfirmPayload, DocumentRow } from "./model";

export const documentsKeys = {
  all: ["documents"] as const,
  list: (page: number, pageSize: number) => ["documents", "list", page, pageSize] as const,
  detail: (id: number) => ["documents", "detail", id] as const,
};

/** Polling interval while the backend is still reading a document. */
const READING_POLL_MS = 2000;
/** The preview link is presigned for 5 minutes; refresh it well before it expires. */
const FILE_URL_REFRESH_MS = 4 * 60 * 1000;

export function useDocumentList(page: number, pageSize: number) {
  return useQuery({
    queryKey: documentsKeys.list(page, pageSize),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/documents", { params: { query: { page, page_size: pageSize } } })),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.parse_status === "pending") ? READING_POLL_MS : false,
  });
}

export function useDocument(id: number) {
  return useQuery({
    queryKey: documentsKeys.detail(id),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
    refetchInterval: (query) =>
      query.state.data?.parse_status === "pending" ? READING_POLL_MS : FILE_URL_REFRESH_MS,
  });
}

export interface UploadVariables {
  file: File;
  /** Fraction of request bytes sent, 0 to 1. */
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

/**
 * POST /api/v1/documents with upload progress. fetch cannot report upload progress, so this
 * one request uses XMLHttpRequest; errors are mapped to ApiError like every other call.
 */
export function uploadDocument({ file, onProgress, signal }: UploadVariables): Promise<DocumentRow> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file, file.name);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/documents");
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.responseType = "text";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress?.(event.loaded / event.total);
    };
    xhr.upload.onload = () => onProgress?.(1);
    xhr.onload = () => {
      let parsed: unknown = undefined;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        // Not JSON (e.g. a proxy error page); fall back to the status message.
      }
      if (xhr.status >= 200 && xhr.status < 300 && parsed) {
        resolve(parsed as DocumentRow);
      } else {
        reject(toApiError(parsed, new Response(null, { status: xhr.status || 502 })));
      }
    };
    xhr.onerror = () => reject(new TypeError("Network request failed"));
    xhr.ontimeout = () => reject(new ApiError(504, "timeout", "The upload timed out. Try again."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException("Upload cancelled", "AbortError"));
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(body);
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents", "list"] });
    },
  });
}

export function useConfirmDocument(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ConfirmPayload) =>
      unwrap(
        await api.POST("/api/v1/documents/{document_id}/confirm", { params: { path: { document_id: id } }, body }),
      ),
    onSettled: () => {
      // Confirmed (or found to be confirmed already): the status and claim link change.
      void queryClient.invalidateQueries({ queryKey: documentsKeys.all });
    },
  });
}

/** A processing run, polled until it finishes. */
export function useRun(id: number | null) {
  return useQuery({
    queryKey: ["runs", id],
    queryFn: async () => unwrap(await api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: id! } } })),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data && query.state.data.status !== "running" ? false : 1500),
  });
}

/** The claim created from a document, with the alerts its processing raised. */
export function useClaimAlerts(claimId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["claims", claimId, "from-document"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/claims/{claim_id}", { params: { path: { claim_id: claimId! } } })),
    enabled: claimId !== null && enabled,
    select: (detail) => detail.alerts,
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ["reference", "providers", "all"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/reference/providers", { params: { query: { page_size: 200 } } })),
    staleTime: Infinity,
  });
}

export function useServiceCodes() {
  return useQuery({
    queryKey: ["reference", "service-codes", "all"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/reference/service-codes", { params: { query: { page_size: 200 } } })),
    staleTime: Infinity,
  });
}
