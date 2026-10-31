"use client";

import { ArrowLeft, FileSpreadsheet, Network, ReceiptText, SearchX, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { AlertAmount, AlertStatusBadge, SeverityBadge } from "@/components/review/badges";
import {
  ClaimStatusBadge,
  claimFacts,
  DuplicateDecisions,
  Facts,
  LinesTable,
  PayableSteps,
  PolicyPanel,
  ResultsByCheck,
  SettlementFacts,
} from "@/components/review/claim-parts";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { type AlertBrief, categoryLabel, claimTypeLabel, describePattern } from "@/lib/alerts/model";
import { useClaim } from "@/lib/claims/hooks";
import type { ClaimDetail } from "@/lib/claims/model";
import { EMPTY, formatDate, formatINR, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const CLAIM_ID_RE = /^[A-Za-z0-9-]{1,40}$/;

function BackLink() {
  return (
    <Link
      href="/alerts"
      className="mb-3 inline-flex items-center gap-1 rounded-sm text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="size-3.5" aria-hidden="true" />
      Alerts
    </Link>
  );
}

export function ClaimDetailView({ id: rawId }: { id: string }) {
  const id = decodeURIComponent(rawId);
  if (!CLAIM_ID_RE.test(id)) return <ClaimNotFound />;
  return <ClaimView id={id} />;
}

function ClaimNotFound() {
  return (
    <>
      <BackLink />
      <EmptyState
        icon={SearchX}
        title="Claim not found"
        description="No claim has this ID. Check the link, or find the claim from its alerts."
        actions={
          <Button asChild variant="outline">
            <Link href="/alerts">Back to Alerts</Link>
          </Button>
        }
      />
    </>
  );
}

function ClaimView({ id }: { id: string }) {
  const query = useClaim(id);
  if (query.isPending) return <ClaimDetailSkeleton />;
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <ClaimNotFound />;
    return <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  }
  const detail = query.data;
  const { claim } = detail;
  const flaggedLines = new Set(detail.alerts.flatMap((a) => (a.line_id ? [a.line_id] : [])));

  return (
    <>
      <BackLink />
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2.5">
            <span className="num">Claim {claim.claim_id}</span>
            <ClaimStatusBadge status={claim.status} />
          </span>
        }
        description={
          <>
            {claim.claimant_name} · {claimTypeLabel(claim.claim_type)} · incident{" "}
            <span className="num">{formatDate(claim.incident_date)}</span>
          </>
        }
        actions={
          <>
            <Button asChild>
              <Link href={`/claims/${encodeURIComponent(claim.claim_id)}/investigate`}>
                <Network data-icon="inline-start" aria-hidden="true" />
                Investigate
              </Link>
            </Button>
            {claim.document_id != null && (
              <Button asChild variant="outline">
                <Link href={`/documents/${claim.document_id}`}>
                  <ReceiptText data-icon="inline-start" aria-hidden="true" />
                  Open document
                </Link>
              </Button>
            )}
            {claim.import_batch_id != null && (
              <Button asChild variant="outline">
                <Link href={`/imports/${claim.import_batch_id}`}>
                  <FileSpreadsheet data-icon="inline-start" aria-hidden="true" />
                  <span className="num">Import #{claim.import_batch_id}</span>
                </Link>
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-4">
        <Totals detail={detail} />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="min-w-0 space-y-4 xl:col-span-2">
            <AlertsPanel alerts={detail.alerts} />
            <Panel aria-labelledby="payable-title">
              <PanelHeader
                title={<span id="payable-title">From requested to payable</span>}
                description="Each policy step in order, with the amount it removed."
              />
              <PayableSteps steps={detail.payable_steps} requested={claim.requested_amount} />
            </Panel>
            <Panel aria-labelledby="results-title">
              <PanelHeader
                title={<span id="results-title">Validation results</span>}
                description="Every check run on this claim, passes included. Failures and adjustments are open."
              />
              <ResultsByCheck results={detail.results} />
            </Panel>
            <Panel aria-labelledby="lines-title">
              <PanelHeader
                title={
                  <span id="lines-title">
                    Lines{" "}
                    <span className="num font-normal text-muted-foreground">{formatNumber(detail.lines.length)}</span>
                  </span>
                }
                description={flaggedLines.size > 0 ? "Lines with an alert are highlighted." : undefined}
              />
              <LinesTable lines={detail.lines} flagged={flaggedLines} caption="Claim lines" />
            </Panel>
          </div>
          <div className="min-w-0 space-y-4">
            <Panel aria-labelledby="claim-facts-title">
              <PanelHeader title={<span id="claim-facts-title">Claim details</span>} />
              <div className="px-4 py-3">
                <Facts items={claimFacts(claim)} />
              </div>
            </Panel>
            {detail.settlement && (
              <Panel aria-labelledby="settlement-title">
                <PanelHeader title={<span id="settlement-title">Settlement</span>} />
                <div className="px-4 py-3">
                  <SettlementFacts settlement={detail.settlement} />
                </div>
              </Panel>
            )}
            <Panel aria-labelledby="duplicates-title">
              <PanelHeader
                title={<span id="duplicates-title">Duplicate checks</span>}
                description="Matches with other claims, including repeats cleared as legitimate."
              />
              <DuplicateDecisions matches={detail.duplicates} claimId={claim.claim_id} />
            </Panel>
            <PolicyPanel policy={detail.policy} />
          </div>
        </div>
      </div>
    </>
  );
}

function Totals({ detail }: { detail: ClaimDetail }) {
  const { claim, settlement, alerts } = detail;
  const items = [
    { label: "Requested", value: formatINR(claim.requested_amount) },
    { label: "Payable after policy terms", value: claim.payable == null ? EMPTY : formatINR(claim.payable) },
    ...(settlement ? [{ label: "Paid", value: formatINR(settlement.paid_amount) }] : []),
    { label: "Alerts", value: formatNumber(alerts.length) },
  ];
  return (
    <ul
      className={cn("grid grid-cols-2 gap-3", items.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3")}
      aria-label="Totals"
    >
      {items.map((item) => (
        <li key={item.label} className="min-w-0 rounded-lg border bg-card px-4 py-3">
          <p className="truncate text-xs text-muted-foreground">{item.label}</p>
          <p className="num mt-0.5 text-lg leading-7 font-semibold">{item.value}</p>
        </li>
      ))}
    </ul>
  );
}

function AlertsPanel({ alerts }: { alerts: AlertBrief[] }) {
  return (
    <Panel aria-labelledby="claim-alerts-title">
      <PanelHeader
        title={
          <span id="claim-alerts-title">
            Alerts <span className="num font-normal text-muted-foreground">{formatNumber(alerts.length)}</span>
          </span>
        }
      />
      {alerts.length === 0 ? (
        <p className="flex items-center gap-2 px-4 py-3 text-[13px] text-muted-foreground">
          <ShieldCheck className="size-4 text-success" aria-hidden="true" />
          No leakage was found on this claim.
        </p>
      ) : (
        <ul className="divide-y">
          {alerts.map((alert) => {
            const pattern = describePattern(alert.rule_or_pattern);
            return (
              <li key={alert.id}>
                <Link
                  href={`/alerts/${alert.id}`}
                  className="grid gap-x-4 gap-y-1.5 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset sm:grid-cols-[minmax(0,1fr)_auto]"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="num text-[13px] font-medium text-primary">#{alert.id}</span>
                      <span className="text-sm font-medium">{categoryLabel(alert.category)}</span>
                      <SeverityBadge severity={alert.severity} />
                      <AlertStatusBadge status={alert.status} />
                    </div>
                    <p className="text-[13px] text-pretty text-muted-foreground">{alert.explanation}</p>
                    <p className="text-xs text-muted-foreground">
                      {pattern.code && <span className="num mr-1">{pattern.code}</span>}
                      {pattern.name}
                      {alert.line_id && <span className="num"> · {alert.line_id}</span>}
                    </p>
                  </div>
                  <AlertAmount
                    amount={alert.amount}
                    type={alert.amount_type}
                    className="sm:justify-end sm:self-start"
                  />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

export function ClaimDetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading claim">
      <Skeleton className="mb-3 h-4 w-16" />
      <div className="mb-5 space-y-2">
        <Skeleton className="h-7 w-64 max-w-full" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-4 xl:col-span-2">
            <Skeleton className="h-40 rounded-lg" />
            <Skeleton className="h-72 rounded-lg" />
          </div>
          <Skeleton className="h-96 rounded-lg" />
        </div>
      </div>
    </div>
  );
}
