"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Panel, PanelHeader } from "@/components/page";
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

/** Seeded lookups that every import is validated against. */
export function ReferenceData() {
  const totals = useReferenceTotals();

  return (
    <Panel aria-labelledby="reference-data-title">
      <PanelHeader
        title={<span id="reference-data-title">Reference data</span>}
        description="Loaded in the database and used to validate every import."
      />
      {totals.isError ? (
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4" role="alert">
          <p className="text-sm text-destructive">{getErrorMessage(totals.error)}</p>
          <Button variant="outline" size="sm" onClick={() => totals.refetch()}>
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            Try again
          </Button>
        </div>
      ) : (
        <dl className="grid grid-cols-2 divide-x">
          <Stat label="Providers" value={totals.data?.providers} />
          <Stat label="Service codes" value={totals.data?.serviceCodes} />
        </dl>
      )}
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="px-4 py-3.5">
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="mt-1 flex h-7 items-center text-xl leading-7 font-semibold num">
        {value === undefined ? <Skeleton className="h-5 w-12" /> : formatNumber(value)}
      </dd>
    </div>
  );
}
