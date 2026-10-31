"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

export const graphKeys = {
  related: (claimId: string) => ["graph", "related", claimId] as const,
  records: (nodeId: string) => ["graph", "records", nodeId] as const,
};

export function useRelated(claimId: string) {
  return useQuery({
    queryKey: graphKeys.related(claimId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/claims/{claim_id}/related", { params: { path: { claim_id: claimId } } })),
  });
}

export function useNodeRecords(nodeId: string | null) {
  return useQuery({
    queryKey: graphKeys.records(nodeId ?? ""),
    enabled: nodeId !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/graph/nodes/{node_id}/records", { params: { path: { node_id: nodeId ?? "" } } }),
      ),
  });
}
