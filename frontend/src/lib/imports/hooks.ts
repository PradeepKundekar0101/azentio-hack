"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { ApiError, toApiError, unwrap } from "@/lib/api/errors";

import type { DatasetHint, ImportBatch, IssueSeverity } from "./model";

export const importsKeys = {
  all: ["imports"] as const,
  list: (page: number, pageSize: number) => ["imports", "list", page, pageSize] as const,
  batch: (id: number) => ["imports", "batch", id] as const,
  issues: (id: number, filters: IssueFilters) => ["imports", "issues", id, filters] as const,
};

export function useImportList(page: number, pageSize: number) {
  return useQuery({
    queryKey: importsKeys.list(page, pageSize),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/imports", { params: { query: { page, page_size: pageSize } } })),
    placeholderData: keepPreviousData,
  });
}

export function useImportBatch(id: number) {
  return useQuery({
    queryKey: importsKeys.batch(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/imports/{batch_id}", { params: { path: { batch_id: id } } })),
    // A batch never changes once processed.
    staleTime: Infinity,
  });
}

export interface IssueFilters {
  dataset: string;
  severity: IssueSeverity | "";
  page: number;
  pageSize: number;
}

export function useImportIssues(id: number, filters: IssueFilters) {
  return useQuery({
    queryKey: importsKeys.issues(id, filters),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/imports/{batch_id}/issues", {
          params: {
            path: { batch_id: id },
            query: {
              dataset: filters.dataset || undefined,
              severity: filters.severity || undefined,
              page: filters.page,
              page_size: filters.pageSize,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
}

/** Same-origin URL of the CSV error report; a plain link sends the session cookie. */
export function issuesCsvUrl(id: number, filters: Pick<IssueFilters, "dataset" | "severity">): string {
  const params = new URLSearchParams();
  if (filters.dataset) params.set("dataset", filters.dataset);
  if (filters.severity) params.set("severity", filters.severity);
  const qs = params.toString();
  return `/api/v1/imports/${id}/issues.csv${qs ? `?${qs}` : ""}`;
}

export interface UploadVariables {
  files: File[];
  dataset?: DatasetHint;
  /** Fraction of request bytes sent, 0 to 1. Reaches 1 before the server finishes processing. */
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

/**
 * POST /api/v1/imports with upload progress. openapi-fetch (fetch) cannot report upload
 * progress, so this one request uses XMLHttpRequest; errors are mapped to ApiError like
 * every other call.
 */
export function uploadImport({ files, dataset, onProgress, signal }: UploadVariables): Promise<ImportBatch> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    const url = dataset ? `/api/v1/imports?dataset=${encodeURIComponent(dataset)}` : "/api/v1/imports";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
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
        resolve(parsed as ImportBatch);
      } else {
        reject(toApiError(parsed, new Response(null, { status: xhr.status || 502 })));
      }
    };
    // Network failures surface as TypeError, which getErrorMessage explains.
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

export function useUploadImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadImport,
    onSuccess: (batch) => {
      queryClient.setQueryData(importsKeys.batch(batch.id), batch);
      void queryClient.invalidateQueries({ queryKey: ["imports", "list"] });
    },
  });
}
