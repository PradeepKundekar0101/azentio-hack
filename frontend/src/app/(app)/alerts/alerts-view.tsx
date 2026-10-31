"use client";

import { ChartColumn, CircleCheck, FilterX, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Pagination, parsePage, parsePageSize, StateMessage, TableStateRows } from "@/components/data-table";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { AmountTypeLegend } from "@/components/review/amount-legend";
import { AlertFilterBar } from "@/components/review/alert-filters";
import { AlertAmount, AlertStatusBadge, SeverityBadge } from "@/components/review/badges";
import { SortHeader } from "@/components/review/sort-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getErrorMessage } from "@/lib/api/errors";
import {
  type AlertFilters,
  type AlertSort,
  countActiveFilters,
  FILTER_URL_DEFAULTS,
  filtersToSearch,
  filtersToUrlPatch,
  parseAlertFilters,
  parseSort,
} from "@/lib/alerts/filters";
import { useAlerts, useClearedDuplicates } from "@/lib/alerts/hooks";
import { type AlertRow, categoryLabel, claimTypeLabel, type ClearedRow, describePattern } from "@/lib/alerts/model";
import { describeSignals } from "@/lib/claims/model";
import { formatDate, formatNumber } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";

/** Filters, sort, page and tab live in the URL so any view can be shared. */
const URL_DEFAULTS = {
  ...FILTER_URL_DEFAULTS,
  sort: "-amount",
  page: "1",
  size: "25",
  tab: "alerts",
  cpage: "1",
};

const ALERT_COLUMNS = 9;
const CLEARED_PAGE_SIZE = 25;

const linkClass =
  "rounded-sm font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring";

export function AlertsView() {
  const [url, setUrl] = useUrlState(URL_DEFAULTS);
  const filters = parseAlertFilters(url);
  const tab = url.tab === "cleared" ? "cleared" : "alerts";
  const cleared = useClearedDuplicates(parsePage(url.cpage), CLEARED_PAGE_SIZE);

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Every detected issue with the rule behind it, its amount and the records that support it."
        actions={
          <Button asChild variant="outline">
            <Link href={`/${filtersToSearch(filters)}`}>
              <ChartColumn data-icon="inline-start" aria-hidden="true" />
              View on dashboard
            </Link>
          </Button>
        }
      />
      <Tabs value={tab} onValueChange={(value) => setUrl({ tab: value })} className="gap-4">
        <TabsList>
          <TabsTrigger value="alerts" className="px-3">
            Alerts
          </TabsTrigger>
          <TabsTrigger value="cleared" className="px-3">
            Cleared
            {cleared.data && (
              <span className="num text-xs font-normal text-muted-foreground">{formatNumber(cleared.data.total)}</span>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="alerts" className="space-y-4">
          <AlertsPanel
            filters={filters}
            sort={parseSort(url.sort)}
            page={parsePage(url.page)}
            pageSize={parsePageSize(url.size)}
            onFilters={(next) => setUrl({ ...filtersToUrlPatch(next), page: "1" })}
            onSort={(sort) => setUrl({ sort, page: "1" })}
            onPage={(page) => setUrl({ page: String(page) })}
            onPageSize={(size) => setUrl({ size: String(size), page: "1" })}
          />
          <AmountTypeLegend />
        </TabsContent>
        <TabsContent value="cleared">
          <ClearedPanel
            query={cleared}
            page={parsePage(url.cpage)}
            onPage={(page) => setUrl({ cpage: String(page) })}
          />
        </TabsContent>
      </Tabs>
    </>
  );
}

function AlertsPanel({
  filters,
  sort,
  page,
  pageSize,
  onFilters,
  onSort,
  onPage,
  onPageSize,
}: {
  filters: AlertFilters;
  sort: AlertSort;
  page: number;
  pageSize: number;
  onFilters: (next: AlertFilters) => void;
  onSort: (sort: AlertSort) => void;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  const alerts = useAlerts(filters, sort, page, pageSize);
  const total = alerts.data?.total;
  const filtered = countActiveFilters(filters) > 0;

  if (total === 0 && !filtered && page === 1) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="No alerts yet"
        description="Alerts are raised when a processed claim breaks a policy rule or duplicates an earlier claim. Import claims data and run validation to get started."
        actions={
          <Button asChild>
            <Link href="/imports">Go to Imports</Link>
          </Button>
        }
      />
    );
  }

  const stateProps = {
    error: alerts.isError ? getErrorMessage(alerts.error) : null,
    onRetry: () => alerts.refetch(),
    emptyIcon: filtered ? FilterX : CircleCheck,
    emptyTitle: filtered ? "No alerts match these filters" : "No alerts on this page",
    emptyHint: filtered ? "Remove a filter or widen a range." : undefined,
  };

  return (
    <Panel id="alerts" aria-labelledby="alerts-title" className="scroll-mt-16">
      <PanelHeader
        title={
          <span id="alerts-title">
            Alerts
            {total !== undefined && (
              <span className="num ml-1.5 font-normal text-muted-foreground">{formatNumber(total)}</span>
            )}
          </span>
        }
        description="Largest amounts first. Open an alert to see the rule, the claim lines and the source rows."
      />
      <AlertFilterBar filters={filters} onChange={onFilters} className="border-b px-4 py-2.5" />
      {/* Phones get a stacked list so amount, type and severity stay in view. */}
      <div className="md:hidden">
        {alerts.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading alerts">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : alerts.isError || alerts.data.items.length === 0 ? (
          <div className="px-4 py-10">
            <StateMessage {...stateProps} />
          </div>
        ) : (
          <ul aria-labelledby="alerts-title" className="divide-y">
            {alerts.data.items.map((alert) => (
              <AlertItem key={alert.id} alert={alert} />
            ))}
          </ul>
        )}
      </div>
      <div className="hidden md:block">
        <Table aria-labelledby="alerts-title" className="min-w-[1040px]">
          <TableHeader>
            <TableRow>
              <SortHeader field="id" sort={sort} onSort={onSort}>
                Alert
              </SortHeader>
              <SortHeader field="category" sort={sort} onSort={onSort}>
                Category
              </SortHeader>
              <SortHeader field="severity" sort={sort} onSort={onSort}>
                Severity
              </SortHeader>
              <SortHeader field="amount" sort={sort} onSort={onSort} align="right">
                Amount
              </SortHeader>
              <SortHeader field="claim_id" sort={sort} onSort={onSort}>
                Claim
              </SortHeader>
              <TableHead>Provider</TableHead>
              <TableHead>Claim type</TableHead>
              <SortHeader field="incident_date" sort={sort} onSort={onSort}>
                Incident date
              </SortHeader>
              <SortHeader field="status" sort={sort} onSort={onSort}>
                Status
              </SortHeader>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableStateRows
              colSpan={ALERT_COLUMNS}
              isLoading={alerts.isPending}
              isEmpty={alerts.data?.items.length === 0}
              {...stateProps}
            />
            {alerts.data?.items.map((alert) => (
              <AlertTableRow key={alert.id} alert={alert} />
            ))}
          </TableBody>
        </Table>
      </div>
      {total !== undefined && total > 0 && (
        <Pagination
          page={page}
          pageSize={pageSize}
          total={total}
          isFetching={alerts.isFetching && !alerts.isPending}
          onPage={(p) => {
            onPage(p);
            const panel = document.getElementById("alerts");
            if (panel && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: "start" });
          }}
          onPageSize={onPageSize}
        />
      )}
    </Panel>
  );
}

function AlertTableRow({ alert }: { alert: AlertRow }) {
  const pattern = describePattern(alert.rule_or_pattern);
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/alerts/${alert.id}`}
          className={linkClass}
          aria-label={`Alert ${alert.id}: ${categoryLabel(alert.category)}`}
        >
          <span className="num">#{alert.id}</span>
        </Link>
      </TableCell>
      <TableCell>
        <Link
          href={`/alerts/${alert.id}`}
          tabIndex={-1}
          className="rounded-sm font-medium outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {categoryLabel(alert.category)}
        </Link>
        {pattern.name.toLowerCase() !== categoryLabel(alert.category).toLowerCase() && (
          <div className="text-xs text-muted-foreground">
            {pattern.code && <span className="num mr-1">{pattern.code}</span>}
            {pattern.name}
          </div>
        )}
      </TableCell>
      <TableCell>
        <SeverityBadge severity={alert.severity} />
      </TableCell>
      <TableCell className="text-right">
        <AlertAmount amount={alert.amount} type={alert.amount_type} badgeFirst className="flex-nowrap justify-end" />
      </TableCell>
      <TableCell>
        <Link href={`/claims/${encodeURIComponent(alert.claim_id)}`} className={linkClass}>
          <span className="num">{alert.claim_id}</span>
        </Link>
        <div className="text-xs text-muted-foreground">{alert.claimant}</div>
      </TableCell>
      <TableCell className="max-w-52">
        <div className="truncate" title={alert.provider_name ?? undefined}>
          {alert.provider_name ?? <span className="text-muted-foreground">–</span>}
        </div>
      </TableCell>
      <TableCell>{claimTypeLabel(alert.claim_type)}</TableCell>
      <TableCell className="num text-muted-foreground">{formatDate(alert.incident_date)}</TableCell>
      <TableCell>
        <AlertStatusBadge status={alert.status} />
      </TableCell>
    </TableRow>
  );
}

function AlertItem({ alert }: { alert: AlertRow }) {
  return (
    <li>
      <Link
        href={`/alerts/${alert.id}`}
        className="block space-y-1.5 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="flex items-center gap-2">
          <span className="num text-sm font-medium text-primary">#{alert.id}</span>
          <SeverityBadge severity={alert.severity} />
          <span className="ml-auto">
            <AlertStatusBadge status={alert.status} />
          </span>
        </div>
        <p className="text-sm font-medium">{categoryLabel(alert.category)}</p>
        <AlertAmount amount={alert.amount} type={alert.amount_type} />
        <p className="num truncate text-xs text-muted-foreground">
          {alert.claim_id} · {alert.claimant} · {formatDate(alert.incident_date)}
        </p>
        {alert.provider_name && <p className="truncate text-xs text-muted-foreground">{alert.provider_name}</p>}
      </Link>
    </li>
  );
}

function ClearedPanel({
  query,
  page,
  onPage,
}: {
  query: ReturnType<typeof useClearedDuplicates>;
  page: number;
  onPage: (page: number) => void;
}) {
  const total = query.data?.total;
  if (total === 0 && page === 1) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No repeats cleared yet"
        description="When a repeated service is legitimate (for example weekly physiotherapy), it is cleared with the reason instead of being flagged. Those decisions appear here."
      />
    );
  }
  const stateProps = {
    error: query.isError ? getErrorMessage(query.error) : null,
    onRetry: () => query.refetch(),
    emptyTitle: "Nothing on this page",
  };
  return (
    <Panel aria-labelledby="cleared-title">
      <PanelHeader
        title={
          <span id="cleared-title">
            Cleared repeats
            {total !== undefined && (
              <span className="num ml-1.5 font-normal text-muted-foreground">{formatNumber(total)}</span>
            )}
          </span>
        }
        description="Repeated services that were checked and found legitimate, with the reason. None of these raised an alert."
      />
      <div className="md:hidden">
        {query.isPending ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading cleared repeats">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : query.isError || query.data.items.length === 0 ? (
          <div className="px-4 py-10">
            <StateMessage {...stateProps} />
          </div>
        ) : (
          <ul aria-labelledby="cleared-title" className="divide-y">
            {query.data.items.map((row) => (
              <li key={row.id} className="space-y-1.5 px-4 py-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <ClaimLink id={row.claim_id} />
                  <span className="text-muted-foreground">repeats</span>
                  <ClaimLink id={row.matched_claim_id} />
                </div>
                <p className="text-sm text-pretty">{row.reason}</p>
                <p className="text-xs text-muted-foreground">
                  {row.service_description ?? "Service"}
                  {row.service_code && <span className="font-mono"> · {row.service_code}</span>} · {row.claimant}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="hidden md:block">
        <Table aria-labelledby="cleared-title" className="min-w-[900px] table-fixed">
          <colgroup>
            <col className="w-32" />
            <col className="w-32" />
            <col className="w-28" />
            <col className="w-52" />
            <col />
            <col className="w-36" />
          </colgroup>
          <TableHeader>
            <TableRow>
              <TableHead>Claim</TableHead>
              <TableHead>Earlier claim</TableHead>
              <TableHead>Claimant</TableHead>
              <TableHead>Service</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Signals</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableStateRows
              colSpan={6}
              isLoading={query.isPending}
              isEmpty={query.data?.items.length === 0}
              {...stateProps}
            />
            {query.data?.items.map((row) => (
              <ClearedTableRow key={row.id} row={row} />
            ))}
          </TableBody>
        </Table>
      </div>
      {total !== undefined && total > CLEARED_PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={CLEARED_PAGE_SIZE}
          total={total}
          isFetching={query.isFetching && !query.isPending}
          onPage={onPage}
        />
      )}
    </Panel>
  );
}

function ClaimLink({ id }: { id: string }) {
  return (
    <Link href={`/claims/${encodeURIComponent(id)}`} className={linkClass}>
      <span className="num">{id}</span>
    </Link>
  );
}

function ClearedTableRow({ row }: { row: ClearedRow }) {
  const signals = describeSignals(row.signals);
  return (
    <TableRow className="align-top">
      <TableCell className="align-top">
        <ClaimLink id={row.claim_id} />
        {row.line_id && <div className="num text-xs text-muted-foreground">{row.line_id}</div>}
      </TableCell>
      <TableCell className="align-top">
        <ClaimLink id={row.matched_claim_id} />
        {row.matched_line_id && <div className="num text-xs text-muted-foreground">{row.matched_line_id}</div>}
      </TableCell>
      <TableCell className="align-top text-muted-foreground">{row.claimant}</TableCell>
      <TableCell className="align-top whitespace-normal">
        <div>{row.service_description ?? "–"}</div>
        {row.service_code && <div className="font-mono text-[11px] text-muted-foreground">{row.service_code}</div>}
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        <p className="text-pretty">{row.reason}</p>
      </TableCell>
      <TableCell className="align-top whitespace-normal">
        {signals.length === 0 ? (
          <span className="text-muted-foreground">–</span>
        ) : (
          <dl className="space-y-0.5 text-xs">
            {signals.map((s) => (
              <div key={s.key}>
                <dt className="inline text-muted-foreground">{s.label}: </dt>
                <dd className="num inline font-medium">{s.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </TableCell>
    </TableRow>
  );
}
