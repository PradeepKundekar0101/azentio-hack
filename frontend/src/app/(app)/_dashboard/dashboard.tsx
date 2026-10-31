"use client";

import { ArrowRight, ChartColumn, FileSpreadsheet, History } from "lucide-react";
import Link from "next/link";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { AmountTypeLegend } from "@/components/review/amount-legend";
import { ActiveFilterChips } from "@/components/review/alert-filters";
import { AmountTypeBadge } from "@/components/review/badges";
import { RunStatus, RunValidationButton, useRunValidation } from "@/components/review/run-validation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api/errors";
import {
  type AlertFilters,
  countActiveFilters,
  FILTER_URL_DEFAULTS,
  filtersToSearch,
  filtersToUrlPatch,
  parseAlertFilters,
} from "@/lib/alerts/filters";
import { useDashboardSummary } from "@/lib/alerts/hooks";
import type { DashboardSummary } from "@/lib/alerts/model";
import { formatDateTime, formatINR, formatINRCompact, formatNumber, formatPercent } from "@/lib/format";
import { useUrlState } from "@/lib/use-url-state";
import { cn } from "@/lib/utils";

import { CategoryChart, ProviderChart, SeverityChart } from "./dashboard-charts";

/** Nothing has been validated yet (filters can also produce zeros, which is not this). */
function isEmpty(summary: DashboardSummary, filtered: boolean): boolean {
  return !filtered && !summary.last_run && summary.kpis.claims_processed === 0;
}

export function Dashboard() {
  const [url, setUrl] = useUrlState(FILTER_URL_DEFAULTS);
  const filters = parseAlertFilters(url);
  const filtered = countActiveFilters(filters) > 0;
  const summary = useDashboardSummary(filters);
  const validation = useRunValidation({ scope: "all" });
  const setFilters = (next: AlertFilters) => setUrl(filtersToUrlPatch(next));

  const runButton = (
    <RunValidationButton
      label="Run validation on all claims"
      isRunning={validation.isRunning}
      onClick={validation.startRun}
    />
  );

  const header = (
    <PageHeader
      title="Dashboard"
      description="Leakage across processed claims, with calculated and estimated amounts kept apart."
      actions={summary.data && !isEmpty(summary.data, filtered) ? runButton : undefined}
    />
  );

  if (summary.isPending) {
    return (
      <>
        {header}
        <DashboardSkeleton />
      </>
    );
  }
  if (summary.isError) {
    return <LoadError message={getErrorMessage(summary.error)} onRetry={() => summary.refetch()} />;
  }

  const data = summary.data;
  const nothingProcessed = isEmpty(data, filtered);

  return (
    <>
      {header}
      <div className="space-y-4">
        <RunStatus run={validation.run} onDismiss={validation.dismiss} showDashboardLink={false} />

        {nothingProcessed ? (
          <EmptyState
            icon={ChartColumn}
            title="No claims processed yet"
            description="Import claims data, then run validation. Key figures, leakage by category and the providers with the most leakage appear here."
            actions={
              <>
                <Button asChild variant="outline">
                  <Link href="/imports">
                    <FileSpreadsheet data-icon="inline-start" aria-hidden="true" />
                    Go to Imports
                  </Link>
                </Button>
                {runButton}
              </>
            }
          />
        ) : (
          <>
            <ActiveFilterChips
              filters={filters}
              onChange={setFilters}
              actions={
                <Button asChild variant="link" size="sm" className="px-1">
                  <Link href={`/alerts${filtersToSearch(filters)}`}>
                    View these alerts
                    <ArrowRight data-icon="inline-end" aria-hidden="true" />
                  </Link>
                </Button>
              }
            />
            <Kpis summary={data} filters={filters} filtered={filtered} />
            <div className="grid gap-4 xl:grid-cols-5">
              <Panel className="min-w-0 xl:col-span-3" aria-labelledby="by-category-title">
                <PanelHeader
                  title={<span id="by-category-title">Alerts and amount by category</span>}
                  description="Number of alerts beside each category. Select a bar to see its alerts."
                />
                <div className="px-4 py-3">
                  <CategoryChart summary={data} filters={filters} />
                </div>
              </Panel>
              <Panel className="min-w-0 xl:col-span-2" aria-labelledby="by-severity-title">
                <PanelHeader
                  title={<span id="by-severity-title">Alerts by severity</span>}
                  description="Critical alerts need attention first."
                />
                <div className="px-4 py-3">
                  <SeverityChart summary={data} filters={filters} />
                </div>
              </Panel>
            </div>
            <div className="grid gap-4 xl:grid-cols-5">
              <Panel className="min-w-0 xl:col-span-3" aria-labelledby="by-provider-title">
                <PanelHeader
                  title={<span id="by-provider-title">Calculated leakage by provider</span>}
                  description="The ten providers with the most calculated leakage."
                />
                <div className="px-4 py-3">
                  <ProviderChart summary={data} filters={filters} />
                </div>
              </Panel>
              <div className="min-w-0 space-y-4 xl:col-span-2">
                <LastRun run={data.last_run} />
                <AmountTypeLegend className="bg-card" />
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Kpis({ summary, filters, filtered }: { summary: DashboardSummary; filters: AlertFilters; filtered: boolean }) {
  const { kpis } = summary;
  const alertsHref = (patch: Partial<AlertFilters>) => `/alerts${filtersToSearch({ ...filters, ...patch })}` as const;
  return (
    <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6" aria-label="Key figures">
      <Kpi
        label="Claims processed"
        value={formatNumber(kpis.claims_processed)}
        note={filtered ? "Matching the filters" : "Validated so far"}
      />
      <Kpi
        label="Flagged claims"
        value={formatNumber(kpis.flagged_claims)}
        note={`${formatPercent(kpis.flagged_percent, { ratio: false })} of processed`}
      />
      <Kpi
        label="Open alerts"
        value={formatNumber(kpis.open_alerts)}
        note="Waiting for review"
        href={alertsHref({ status: ["open"] })}
      />
      <Kpi
        label="Calculated leakage"
        value={formatINRCompact(kpis.calculated_leakage)}
        title={formatINR(kpis.calculated_leakage)}
        badge="calculated"
        note={formatINR(kpis.calculated_leakage)}
        href={alertsHref({ amount_type: ["calculated"] })}
      />
      <Kpi
        label="Estimated leakage"
        value={formatINRCompact(kpis.estimated_leakage)}
        title={formatINR(kpis.estimated_leakage)}
        badge="estimated"
        note="For review, not deducted"
        href={alertsHref({ amount_type: ["estimated"] })}
      />
      <Kpi
        label="Suspected alerts"
        value={formatNumber(kpis.suspected_alerts)}
        badge="suspected"
        note="Patterns with no amount"
        href={alertsHref({ amount_type: ["suspected"] })}
      />
    </ul>
  );
}

function Kpi({
  label,
  value,
  note,
  badge,
  href,
  title,
}: {
  label: string;
  value: string;
  note: string;
  badge?: string;
  href?: React.ComponentProps<typeof Link>["href"];
  title?: string;
}) {
  const body = (
    <>
      <div className="flex min-h-5 items-start justify-between gap-2">
        <h3 className="text-[13px] font-medium text-muted-foreground">{label}</h3>
        {badge && <AmountTypeBadge type={badge} className="hidden sm:inline-flex" />}
      </div>
      <p className="num mt-1.5 text-2xl leading-8 font-semibold tracking-[-0.01em]" title={title}>
        {value}
      </p>
      <p className="num mt-0.5 truncate text-xs text-muted-foreground">{note}</p>
      {badge && <AmountTypeBadge type={badge} className="mt-2 sm:hidden" />}
    </>
  );
  const className = "flex h-full flex-col rounded-xl bg-card p-4 text-card-foreground shadow-card";
  return (
    <li className="min-w-0">
      {href ? (
        <Link
          href={href}
          className={cn(
            className,
            "outline-none transition-[box-shadow,transform,background-color] duration-200 hover:-translate-y-px hover:bg-accent/30 hover:shadow-raised focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          {body}
        </Link>
      ) : (
        <div className={className}>{body}</div>
      )}
    </li>
  );
}

function LastRun({ run }: { run: DashboardSummary["last_run"] }) {
  return (
    <Panel aria-labelledby="last-run-title">
      <PanelHeader title={<span id="last-run-title">Last processing run</span>} />
      {run ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 text-[13px]">
          <div>
            <dt className="text-xs text-muted-foreground">Finished</dt>
            <dd className="num mt-0.5 font-medium">
              {run.status === "running" ? "Still running" : formatDateTime(run.finished_at ?? run.started_at)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Scope</dt>
            <dd className="mt-0.5 font-medium">{run.scope === "batch" ? "One import" : "All claims"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Claims processed</dt>
            <dd className="num mt-0.5 font-medium">{formatNumber(run.claims_processed)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Status</dt>
            <dd className={cn("mt-0.5 font-medium", run.status === "failed" && "text-destructive")}>
              {run.status === "completed" ? "Completed" : run.status === "failed" ? "Failed" : "Running"}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="flex items-center gap-2 px-4 py-3 text-[13px] text-muted-foreground">
          <History className="size-4" aria-hidden="true" />
          No run yet.
        </p>
      )}
    </Panel>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-5">
        <Skeleton className="h-80 rounded-lg xl:col-span-3" />
        <Skeleton className="h-80 rounded-lg xl:col-span-2" />
      </div>
    </div>
  );
}
