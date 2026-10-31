"use client";

import { CircleCheck, CircleDashed, FilterX, Search, ShieldAlert, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { FilterSelect, Pagination, parsePage, parsePageSize, StateMessage, TableStateRows } from "@/components/data-table";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { SeverityBadge } from "@/components/review/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { claimTypeLabel } from "@/lib/alerts/model";
import { getErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { useClaims } from "@/lib/claims/hooks";
import {
  CLAIM_SORTS,
  type ClaimReview,
  isNothingPayable,
  NOTHING_PAYABLE_HINT,
  parseClaimSort,
  parseReview,
  parseStatus,
  REVIEW_HINTS,
  reviewLabel,
} from "@/lib/claims/review";
import { EMPTY, formatDate, formatINR, formatNumber } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

type ClaimRow = components["schemas"]["ClaimRow"];

const URL_DEFAULTS = { status: "open", review: "", q: "", sort: "-incident_date", page: "1", size: "25" };
const COLUMNS = 8;

const REVIEW_OPTIONS = [
  { value: "clean", label: "Clean, ready to pay" },
  { value: "flagged", label: "Flagged" },
  { value: "not_validated", label: "Not validated" },
] as const;

const linkClass =
  "rounded-sm font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring";

const REVIEW_STYLE: Record<ClaimReview, { icon: typeof CircleCheck; variant: "success" | "secondary"; className?: string }> = {
  clean: { icon: CircleCheck, variant: "success" },
  flagged: { icon: ShieldAlert, variant: "secondary", className: "bg-destructive/10 text-destructive dark:bg-destructive/20" },
  not_validated: { icon: CircleDashed, variant: "secondary", className: "text-muted-foreground" },
};

export function ReviewBadge({
  review,
  payable,
  className,
}: {
  review: string;
  payable?: string | null;
  className?: string;
}) {
  const style = REVIEW_STYLE[review as ClaimReview] ?? REVIEW_STYLE.not_validated;
  const Icon = style.icon;
  const nothing = isNothingPayable(review, payable);
  return (
    <Badge
      variant={style.variant}
      className={cn("gap-1", style.className, nothing && "bg-success/[0.06] text-success/80", className)}
      title={nothing ? NOTHING_PAYABLE_HINT : REVIEW_HINTS[review as ClaimReview]}
    >
      <Icon aria-hidden="true" />
      {reviewLabel(review, payable)}
    </Badge>
  );
}

function money(value: string | null | undefined) {
  return value === null || value === undefined ? EMPTY : formatINR(value);
}

export function ClaimsView() {
  const [url, setUrl] = useUrlState(URL_DEFAULTS);
  const status = parseStatus(url.status);
  const review = parseReview(url.review);
  const sort = parseClaimSort(url.sort);
  const page = parsePage(url.page);
  const pageSize = parsePageSize(url.size);
  const [search, setSearch] = useState(url.q);

  // Search as you type, without a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      if (search.trim() !== url.q) setUrl({ q: search.trim(), page: "1" });
    }, 300);
    return () => clearTimeout(handle);
  }, [search, url.q, setUrl]);

  const claims = useClaims({ status, review, q: url.q, sort, page, pageSize });
  const total = claims.data?.total;
  const filtered = review !== "all" || url.q !== "";

  const stateProps = {
    error: claims.isError ? getErrorMessage(claims.error) : null,
    onRetry: () => claims.refetch(),
    emptyIcon: filtered ? FilterX : Wallet,
    emptyTitle: filtered ? "No claims match these filters" : "No claims here",
    emptyHint: filtered ? "Clear the search or choose another result." : undefined,
  };

  if (total === 0 && !filtered && status === "all" && page === 1) {
    return (
      <>
        <PageHeader title="Claims" description="Every claim with its validation result and payable amount." />
        <EmptyState
          icon={Wallet}
          title="No claims yet"
          description="Import claims data, then run validation to see which claims are clean and ready to pay."
          actions={
            <Button asChild>
              <Link href="/imports">Go to Imports</Link>
            </Button>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Claims"
        description="Open claims waiting to be settled, with what the policy actually owes. Clean claims can be paid as shown; flagged ones need review first."
      />
      <Tabs value={status} onValueChange={(value) => setUrl({ status: value, page: "1" })} className="gap-4">
        <TabsList>
          <TabsTrigger value="open" className="px-3">
            Open to settle
          </TabsTrigger>
          <TabsTrigger value="settled" className="px-3">
            Settled
          </TabsTrigger>
          <TabsTrigger value="all" className="px-3">
            All
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <Panel id="claims" aria-labelledby="claims-title" className="mt-4 scroll-mt-16">
        <PanelHeader
          title={
            <span id="claims-title">
              {status === "open" ? "Open claims" : status === "settled" ? "Settled claims" : "All claims"}
              {total !== undefined && (
                <span className="num ml-1.5 font-normal text-muted-foreground">{formatNumber(total)}</span>
              )}
            </span>
          }
          description="Payable is the amount after coverage, sub-limits, deductible, co-pay and the overall limit."
        />
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Claim, claimant or policy"
              aria-label="Search claims by claim ID, claimant ID or policy number"
              className="h-8 bg-card pl-8 text-[13px]"
            />
          </div>
          <FilterSelect
            label="Result"
            value={review === "all" ? "" : review}
            onChange={(value) => setUrl({ review: value, page: "1" })}
            options={REVIEW_OPTIONS}
            allLabel="All results"
          />
          <FilterSelect
            label="Sort"
            value={sort}
            onChange={(value) => setUrl({ sort: value || "-incident_date", page: "1" })}
            options={CLAIM_SORTS}
            allLabel="Newest incident"
            className="sm:ml-auto"
          />
        </div>
        {/* Phones get a stacked list so the result and amounts stay in view. */}
        <div className="md:hidden">
          {claims.isPending ? (
            <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading claims">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : claims.isError || claims.data.items.length === 0 ? (
            <div className="px-4 py-10">
              <StateMessage {...stateProps} />
            </div>
          ) : (
            <ul aria-labelledby="claims-title" className="divide-y">
              {claims.data.items.map((claim) => (
                <ClaimItem key={claim.claim_id} claim={claim} />
              ))}
            </ul>
          )}
        </div>
        <div className="hidden md:block">
          <Table aria-labelledby="claims-title" className="min-w-[960px]">
            <TableHeader>
              <TableRow>
                <TableHead>Claim</TableHead>
                <TableHead>Result</TableHead>
                <TableHead>Claim type</TableHead>
                <TableHead>Incident date</TableHead>
                <TableHead className="text-right">Requested</TableHead>
                <TableHead className="text-right">Payable</TableHead>
                <TableHead className="text-right">Leakage</TableHead>
                <TableHead>Alerts</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableStateRows
                colSpan={COLUMNS}
                isLoading={claims.isPending}
                isEmpty={claims.data?.items.length === 0}
                {...stateProps}
              />
              {claims.data?.items.map((claim) => (
                <ClaimTableRow key={claim.claim_id} claim={claim} />
              ))}
            </TableBody>
          </Table>
        </div>
        {total !== undefined && total > 0 && (
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            isFetching={claims.isFetching && !claims.isPending}
            onPage={(p) => {
              setUrl({ page: String(p) });
              const panel = document.getElementById("claims");
              if (panel && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: "start" });
            }}
            onPageSize={(size) => setUrl({ size: String(size), page: "1" })}
          />
        )}
      </Panel>
    </>
  );
}

function Leakage({ claim }: { claim: ClaimRow }) {
  const calculated = Number(claim.calculated_leakage);
  const estimated = Number(claim.estimated_leakage);
  if (!calculated && !estimated) return <span className="text-muted-foreground">{EMPTY}</span>;
  return (
    <div className="space-y-0.5">
      {calculated > 0 && <div className="num">{formatINR(claim.calculated_leakage)}</div>}
      {estimated > 0 && (
        <div className="num text-xs text-muted-foreground" title="Estimated, for review">
          ≈ {formatINR(claim.estimated_leakage)}
        </div>
      )}
    </div>
  );
}

function ClaimTableRow({ claim }: { claim: ClaimRow }) {
  return (
    <TableRow className={cn(claim.review === "clean" && Number(claim.payable) > 0 && "bg-success/[0.04]")}>
      <TableCell>
        <Link href={`/claims/${encodeURIComponent(claim.claim_id)}`} className={linkClass}>
          <span className="num">{claim.claim_id}</span>
        </Link>
        <div className="text-xs text-muted-foreground">
          {claim.claimant} · <span className="num">{claim.policy_number}</span>
        </div>
      </TableCell>
      <TableCell>
        <ReviewBadge review={claim.review} payable={claim.payable} />
      </TableCell>
      <TableCell>{claimTypeLabel(claim.claim_type)}</TableCell>
      <TableCell className="num text-muted-foreground">{formatDate(claim.incident_date)}</TableCell>
      <TableCell className="num text-right">{formatINR(claim.requested_amount)}</TableCell>
      <TableCell
        className={cn(
          "num text-right font-medium",
          claim.review === "clean" && Number(claim.payable) > 0 && "text-success",
          isNothingPayable(claim.review, claim.payable) && "text-muted-foreground",
        )}
      >
        {money(claim.payable)}
      </TableCell>
      <TableCell className="text-right">
        <Leakage claim={claim} />
      </TableCell>
      <TableCell>
        {claim.alerts > 0 ? (
          <div className="flex items-center gap-1.5">
            {claim.top_severity && <SeverityBadge severity={claim.top_severity} />}
            <span className="num text-xs text-muted-foreground">
              {formatNumber(claim.alerts)} {claim.alerts === 1 ? "alert" : "alerts"}
              {claim.open_alerts < claim.alerts && ` · ${formatNumber(claim.open_alerts)} open`}
            </span>
          </div>
        ) : (
          <span className="text-muted-foreground">{EMPTY}</span>
        )}
      </TableCell>
    </TableRow>
  );
}

function ClaimItem({ claim }: { claim: ClaimRow }) {
  return (
    <li>
      <Link
        href={`/claims/${encodeURIComponent(claim.claim_id)}`}
        className="block space-y-1.5 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="flex items-center gap-2">
          <span className="num text-sm font-medium text-primary">{claim.claim_id}</span>
          <span className="ml-auto">
            <ReviewBadge review={claim.review} payable={claim.payable} />
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-3 text-sm">
          <span className="text-muted-foreground">
            Requested <span className="num text-foreground">{formatINR(claim.requested_amount)}</span>
          </span>
          <span className="text-muted-foreground">
            Payable{" "}
            <span
              className={cn(
                "num font-medium text-foreground",
                claim.review === "clean" && Number(claim.payable) > 0 && "text-success",
              )}
            >
              {money(claim.payable)}
            </span>
          </span>
        </div>
        <p className="num truncate text-xs text-muted-foreground">
          {claim.claimant} · {claimTypeLabel(claim.claim_type)} · {formatDate(claim.incident_date)}
          {claim.alerts > 0 && ` · ${formatNumber(claim.alerts)} ${claim.alerts === 1 ? "alert" : "alerts"}`}
        </p>
      </Link>
    </li>
  );
}
