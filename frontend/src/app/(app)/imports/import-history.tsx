"use client";

import { History } from "lucide-react";
import Link from "next/link";

import { Pagination, parsePage, StateMessage, TableStateRows } from "@/components/data-table";
import { EmptyState } from "@/components/empty-state";
import { Panel, PanelHeader } from "@/components/page";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorMessage } from "@/lib/api/errors";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useImportList } from "@/lib/imports/hooks";
import type { ImportBatch } from "@/lib/imports/model";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

import { BatchStatusBadge, ReconciliationBar } from "./import-status";

const PAGE_SIZE = 10;
const URL_DEFAULTS = { page: "1" };
const COLUMNS = 8;

/** Past import batches, newest first, each linking to its reconciliation and issues. */
export function ImportHistory() {
  const [url, setUrl] = useUrlState(URL_DEFAULTS);
  const page = parsePage(url.page);
  const list = useImportList(page, PAGE_SIZE);
  const total = list.data?.total;

  if (total === 0 && page === 1) {
    return (
      <EmptyState
        icon={History}
        title="No imports yet"
        description="Each upload appears here with how many rows were received, accepted, accepted with warnings and rejected."
        className="py-10 sm:py-12"
      />
    );
  }

  return (
    <Panel aria-labelledby="history-title">
      <PanelHeader
        title={<span id="history-title">Recent imports</span>}
        description="Every row of every upload is accounted for. Open an import to see its issues."
      />
      {/* Phones get a stacked list so the counts and status stay in view. */}
      <div className="md:hidden">
        {list.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading imports">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : list.isError ? (
          <div className="px-4 py-10">
            <StateMessage error={getErrorMessage(list.error)} onRetry={() => list.refetch()} />
          </div>
        ) : (
          <ul aria-labelledby="history-title" className="divide-y">
            {list.data.items.map((batch) => (
              <HistoryItem key={batch.id} batch={batch} />
            ))}
          </ul>
        )}
      </div>
      <div className="hidden md:block">
        <Table aria-labelledby="history-title" className="min-w-[760px]">
          <TableHeader>
            <TableRow>
              <TableHead>Import</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead>Files</TableHead>
              <TableHead className="text-right">Received</TableHead>
              <TableHead className="text-right">Accepted</TableHead>
              <TableHead className="text-right">Warnings</TableHead>
              <TableHead className="text-right">Rejected</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableStateRows
              colSpan={COLUMNS}
              isLoading={list.isPending}
              error={list.isError ? getErrorMessage(list.error) : null}
              onRetry={() => list.refetch()}
              isEmpty={list.data?.items.length === 0}
              emptyTitle="No imports on this page"
              skeletonRows={4}
            />
            {list.data?.items.map((batch) => <HistoryRow key={batch.id} batch={batch} />)}
          </TableBody>
        </Table>
      </div>
      {total !== undefined && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          isFetching={list.isFetching}
          onPage={(p) => setUrl({ page: String(p) })}
        />
      )}
    </Panel>
  );
}

function HistoryRow({ batch }: { batch: ImportBatch }) {
  const href = `/imports/${batch.id}` as const;
  const [first, ...rest] = batch.files;
  const { totals } = batch;
  return (
    <TableRow>
      <TableCell>
        <Link
          href={href}
          aria-label={`Import ${batch.id}`}
          className="rounded-sm font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="num">#{batch.id}</span>
        </Link>
      </TableCell>
      <TableCell className="num text-muted-foreground">{formatDateTime(batch.uploaded_at)}</TableCell>
      <TableCell className="max-w-64">
        {first ? (
          <div className="flex min-w-0 items-baseline gap-1.5">
            <span className="truncate" title={batch.files.map((f) => f.file_name).join(", ")}>
              {first.file_name}
            </span>
            {rest.length > 0 && (
              <span className="num shrink-0 text-xs text-muted-foreground">+{formatNumber(rest.length)} more</span>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground">No files</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="inline-flex flex-col items-end gap-1">
          <span className="num font-medium">{formatNumber(totals.received)}</span>
          <ReconciliationBar counts={totals} className="h-1 w-16" />
        </div>
      </TableCell>
      <CountCell value={totals.accepted} />
      <CountCell value={totals.warnings} tone="text-warning" />
      <CountCell value={totals.rejected} tone="text-destructive" />
      <TableCell>
        <BatchStatusBadge status={batch.status} />
      </TableCell>
    </TableRow>
  );
}

function HistoryItem({ batch }: { batch: ImportBatch }) {
  const { totals } = batch;
  const [first, ...rest] = batch.files;
  return (
    <li>
      <Link
        href={`/imports/${batch.id}`}
        className="block space-y-2 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="flex items-center gap-2">
          <span className="num text-sm font-medium text-primary">#{batch.id}</span>
          <BatchStatusBadge status={batch.status} />
          <span className="num ml-auto text-xs text-muted-foreground">{formatDateTime(batch.uploaded_at)}</span>
        </div>
        <div className="flex min-w-0 items-baseline gap-1.5 text-[13px]">
          <span className="truncate">{first?.file_name ?? "No files"}</span>
          {rest.length > 0 && (
            <span className="num shrink-0 text-xs text-muted-foreground">+{formatNumber(rest.length)} more</span>
          )}
        </div>
        <ReconciliationBar counts={totals} className="h-1.5" />
        <p className="num text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{formatNumber(totals.received)}</span> received ·{" "}
          {formatNumber(totals.accepted)} accepted · {formatNumber(totals.warnings)}{" "}
          {totals.warnings === 1 ? "warning" : "warnings"} · {formatNumber(totals.rejected)} rejected
        </p>
      </Link>
    </li>
  );
}

function CountCell({ value, tone }: { value: number; tone?: string }) {
  return (
    <TableCell className={cn("num text-right", value === 0 ? "text-muted-foreground" : tone)}>
      {formatNumber(value)}
    </TableCell>
  );
}
