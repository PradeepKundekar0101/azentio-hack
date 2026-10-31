"use client";

import type { LucideIcon } from "lucide-react";
import { ChevronLeft, ChevronRight, CircleAlert, Inbox, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

interface StateProps {
  isLoading: boolean;
  error?: string | null;
  isEmpty: boolean;
  onRetry?: () => void;
  emptyIcon?: LucideIcon;
  emptyTitle?: string;
  emptyHint?: React.ReactNode;
}

/** The error or empty message shown in place of rows, as a centred block. */
export function StateMessage({
  error,
  onRetry,
  emptyIcon: EmptyIcon = Inbox,
  emptyTitle = "Nothing to show",
  emptyHint,
}: Omit<StateProps, "isLoading" | "isEmpty">) {
  if (error) {
    return (
      <div className="mx-auto flex max-w-sm flex-col items-center text-center" role="alert">
        <CircleAlert className="mb-2 size-5 text-destructive" aria-hidden="true" />
        <p className="text-sm font-medium">Could not load this table</p>
        <p className="mt-0.5 text-[13px] text-muted-foreground">{error}</p>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            Try again
          </Button>
        )}
      </div>
    );
  }
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center text-center">
      <EmptyIcon className="mb-2 size-5 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-medium">{emptyTitle}</p>
      {emptyHint && <p className="mt-0.5 text-[13px] text-pretty text-muted-foreground">{emptyHint}</p>}
    </div>
  );
}

/** Loading, error and empty rows that span the table. Returns null when there are rows to show. */
export function TableStateRows({
  colSpan,
  isLoading,
  error,
  isEmpty,
  skeletonRows = 6,
  ...message
}: StateProps & { colSpan: number; skeletonRows?: number }) {
  if (isLoading) {
    return (
      <>
        {Array.from({ length: skeletonRows }, (_, i) => (
          <TableRow key={i} className="hover:bg-transparent" aria-hidden="true">
            <TableCell colSpan={colSpan}>
              <Skeleton className="h-4 w-full" style={{ opacity: 1 - i * 0.1 }} />
            </TableCell>
          </TableRow>
        ))}
      </>
    );
  }
  if (!error && !isEmpty) return null;
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className="h-40 whitespace-normal">
        <StateMessage error={error} {...message} />
      </TableCell>
    </TableRow>
  );
}

export const PAGE_SIZES = [25, 50, 100] as const;

/** Reads a page size from the URL, falling back to the default for anything unexpected. */
export function parsePageSize(value: string, fallback: number = PAGE_SIZES[0]): number {
  const n = Number(value);
  return (PAGE_SIZES as readonly number[]).includes(n) ? n : fallback;
}

/** Reads a 1-based page number from the URL. */
export function parsePage(value: string): number {
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  isFetching,
  className,
}: {
  page: number;
  pageSize: number;
  total: number | undefined;
  onPage: (page: number) => void;
  onPageSize?: (size: number) => void;
  isFetching?: boolean;
  className?: string;
}) {
  const pages = total ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = total ? Math.min(total, page * pageSize) : 0;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t px-4 py-2 text-[13px] text-muted-foreground",
        className,
      )}
    >
      <div className="num" aria-live="polite">
        {total === undefined
          ? "Loading"
          : total === 0
            ? "No results"
            : `${formatNumber(from)}–${formatNumber(to)} of ${formatNumber(total)}`}
        {isFetching && total !== undefined && <span className="ml-2 text-xs">Updating</span>}
      </div>
      <div className="flex items-center gap-3">
        {onPageSize && (
          <div className="flex items-center gap-2">
            <span aria-hidden="true">Rows</span>
            <Select value={String(pageSize)} onValueChange={(v) => onPageSize(Number(v))}>
              <SelectTrigger size="sm" className="w-[4.5rem] bg-card" aria-label="Rows per page">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            className="bg-card"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <span className="num min-w-[5.5rem] text-center">
            Page {formatNumber(page)} of {formatNumber(pages)}
          </span>
          <Button
            variant="outline"
            size="icon-sm"
            className="bg-card"
            aria-label="Next page"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/** A labelled select with an "All" option. `value` "" means no filter. */
export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel = "All",
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  allLabel?: string;
  className?: string;
}) {
  return (
    <Select value={value || "__all"} onValueChange={(v) => onChange(v === "__all" ? "" : v)}>
      <SelectTrigger
        size="sm"
        aria-label={label}
        className={cn("min-w-32 bg-card text-[13px]", value && "border-primary/50", className)}
      >
        <span className="text-muted-foreground">{label}:</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper" align="start">
        <SelectItem value="__all">{allLabel}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
