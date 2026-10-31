"use client";

import { ArrowRight, ChevronLeft, ChevronRight, ScrollText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { claimTypeLabel } from "@/lib/alerts/model";
import { getErrorMessage } from "@/lib/api/errors";
import { useInvestigations } from "@/lib/evidence/hooks";
import { KIND_LABELS, type EvidenceKind, relativeTime, shortHash } from "@/lib/evidence/model";
import { formatDateTime, formatNumber } from "@/lib/format";

const PAGE_SIZE = 25;

export function EvidenceList() {
  const [page, setPage] = useState(1);
  const query = useInvestigations(page, PAGE_SIZE);

  return (
    <>
      <PageHeader
        title="Evidence"
        description="Every claim under investigation, with a sealed history of calculations, decisions, overrides and notes."
      />
      {query.isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : query.isError ? (
        <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : query.data.total === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No investigations yet"
          description="An investigation opens the first time someone decides a finding, overrides a recommended correction or adds a note. Start from an alert."
          actions={
            <Button asChild>
              <Link href="/alerts">
                Go to Alerts
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </Link>
            </Button>
          }
        />
      ) : (
        <Panel className="overflow-hidden">
          <ul className="divide-y">
            {query.data.items.map((row) => (
              <li key={row.claim_id}>
                <Link
                  href={`/claims/${encodeURIComponent(row.claim_id)}/evidence`}
                  className="grid gap-x-6 gap-y-1 px-4 py-3.5 outline-none hover:bg-muted/50 focus-visible:bg-muted/60 sm:grid-cols-[minmax(10rem,1fr)_2fr_auto]"
                >
                  <div className="min-w-0">
                    <p className="num text-sm font-semibold">{row.claim_id}</p>
                    <p className="truncate text-[13px] text-muted-foreground">
                      {row.claimant_name} · {claimTypeLabel(row.claim_type)}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-[13px]">
                      {row.last_event_kind && (
                        <span className="font-medium">{KIND_LABELS[row.last_event_kind as EvidenceKind]}: </span>
                      )}
                      <span className="text-muted-foreground">{row.last_event_summary}</span>
                    </p>
                    <p className="text-[12px] text-muted-foreground">
                      {row.last_actor} · <span title={formatDateTime(row.last_event_at)}>{relativeTime(row.last_event_at)}</span>
                      {" · opened by "}
                      {row.opened_by} <span className="num">{formatDateTime(row.opened_at)}</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-4 sm:justify-end">
                    <span className="num text-[13px] text-muted-foreground">
                      <span className="font-semibold text-foreground">{formatNumber(row.events)}</span> entries
                    </span>
                    <span className="hidden font-mono text-[11px] text-muted-foreground md:inline">
                      {shortHash(row.head_hash)}
                    </span>
                    <ArrowRight className="size-4 text-muted-foreground" aria-hidden="true" />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          {query.data.total > PAGE_SIZE && (
            <div className="flex items-center justify-between border-t px-4 py-2.5 text-[13px] text-muted-foreground">
              <span className="num">
                {formatNumber((page - 1) * PAGE_SIZE + 1)}–{formatNumber(Math.min(page * PAGE_SIZE, query.data.total))} of{" "}
                {formatNumber(query.data.total)}
              </span>
              <div className="flex gap-1">
                <Button variant="outline" size="icon" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft aria-hidden="true" />
                  <span className="sr-only">Previous page</span>
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  disabled={page * PAGE_SIZE >= query.data.total}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight aria-hidden="true" />
                  <span className="sr-only">Next page</span>
                </Button>
              </div>
            </div>
          )}
        </Panel>
      )}
    </>
  );
}
