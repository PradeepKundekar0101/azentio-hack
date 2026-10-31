"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { RelatedClaimsGraph } from "@/components/investigation/related-claims-graph";
import { PageHeader } from "@/components/page";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * A simple page hosting the reusable investigation components for one claim, until the investigation workspace
 * embeds them.
 */
export function InvestigationView({ id }: { id: string }) {
  return (
    <>
      <Link
        href={`/claims/${encodeURIComponent(id)}`}
        className="mb-3 inline-flex items-center gap-1 rounded-sm text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Claim <span className="num">{id}</span>
      </Link>
      <PageHeader
        title={
          <>
            Investigate <span className="num">{id}</span>
          </>
        }
        description="Related claims, supporting documents and the recommended settlement for this claim."
      />
      <div className="space-y-4">
        <RelatedClaimsGraph claimId={id} />
      </div>
    </>
  );
}

export function InvestigationSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-[520px] w-full" />
    </div>
  );
}
