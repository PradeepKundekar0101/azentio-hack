"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { getErrorMessage, unwrap } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";

// Only the totals are needed, so ask for the smallest page.
const COUNT_ONLY = { params: { query: { page_size: 1 } } };

function useReferenceTotals() {
  return useQuery({
    queryKey: ["reference", "totals"],
    queryFn: async () => {
      const [providers, serviceCodes] = await Promise.all([
        api.GET("/api/v1/reference/providers", COUNT_ONLY).then(unwrap),
        api.GET("/api/v1/reference/service-codes", COUNT_ONLY).then(unwrap),
      ]);
      return { providers: providers.total, serviceCodes: serviceCodes.total };
    },
    staleTime: 5 * 60_000,
  });
}

/** Seeded lookups that every import is validated against, as one compact strip. */
export function ReferenceData() {
  const totals = useReferenceTotals();

  return (
    <Panel
      aria-labelledby="reference-data-title"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3"
    >
      <div className="min-w-0">
        <h2 id="reference-data-title" className="text-sm font-semibold">
          Reference data
        </h2>
        <p className="mt-0.5 text-[13px] text-pretty text-muted-foreground">
          Loaded in the database and used to validate every import.
        </p>
      </div>
      {totals.isError ? (
        <div className="flex flex-wrap items-center gap-3" role="alert">
          <p className="text-[13px] text-destructive">{getErrorMessage(totals.error)}</p>
          <Button variant="outline" size="sm" onClick={() => totals.refetch()}>
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            Try again
          </Button>
        </div>
      ) : (
        <dl className="flex items-center gap-6">
          <Stat label="Providers" value={totals.data?.providers} />
          <Stat label="Service codes" value={totals.data?.serviceCodes} />
        </dl>
      )}
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="flex h-6 items-center text-base leading-6 font-semibold num">
        {value === undefined ? <Skeleton className="h-4 w-10" /> : formatNumber(value)}
      </dd>
    </div>
  );
}
