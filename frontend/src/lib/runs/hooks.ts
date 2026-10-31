"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Schemas } from "@/lib/api/client";
import { ApiError, unwrap } from "@/lib/api/errors";

export type Run = Schemas["RunOut"];
export type RunScope = { scope: "all" } | { scope: "batch"; batchId: number };

/** How often a running validation run is polled. */
export const RUN_POLL_MS = 1_000;

export const runsKeys = {
  all: ["runs"] as const,
  run: (id: number) => ["runs", "run", id] as const,
  latest: ["runs", "latest"] as const,
};

/** True for the 409 the API returns while another run is still processing. */
export function isRunInProgress(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

/** Run ID named in a 409 "Run 12 is still in progress" message, if any. */
export function runningRunId(error: unknown): number | null {
  if (!(error instanceof ApiError)) return null;
  const match = /Run (\d+)/.exec(error.message);
  return match ? Number(match[1]) : null;
}

/**
 * Polls a run until it finishes. When it does, everything computed from runs (alerts,
 * dashboard, claims) is refreshed once.
 */
export function useRun(id: number | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: runsKeys.run(id ?? 0),
    enabled: id !== null,
    queryFn: async () => {
      const run = unwrap(await api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: id as number } } }));
      if (run.status !== "running") {
        const previous = queryClient.getQueryData<Run>(runsKeys.run(run.id));
        if (!previous || previous.status === "running") invalidateRunResults(queryClient);
      }
      return run;
    },
    refetchInterval: (query) => (query.state.data?.status === "running" ? RUN_POLL_MS : false),
    staleTime: 0,
  });
}

function invalidateRunResults(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["alerts"] });
  void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  void queryClient.invalidateQueries({ queryKey: ["claims"] });
  void queryClient.invalidateQueries({ queryKey: runsKeys.latest });
}

export function useLatestRun() {
  return useQuery({
    queryKey: runsKeys.latest,
    queryFn: async () => unwrap(await api.GET("/api/v1/runs/latest")),
  });
}

/** POST /runs. The new run is seeded into the cache so polling starts without a request. */
export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (scope: RunScope) =>
      unwrap(
        await api.POST("/api/v1/runs", {
          body: scope.scope === "all" ? { scope: "all" } : { scope: "batch", batch_id: scope.batchId },
        }),
      ),
    onSuccess: (run) => {
      queryClient.setQueryData(runsKeys.run(run.id), run);
    },
  });
}
