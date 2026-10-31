"use client";

import { ArrowRight, CircleAlert, CircleCheck, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Panel, PanelHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api/errors";
import { useClaimAlerts, useRun } from "@/lib/documents/hooks";
import { alertCategoryLabel, optionLabel } from "@/lib/documents/model";
import { formatINR, formatNumber } from "@/lib/format";

function SeverityBadge({ severity }: { severity: string }) {
  const variant =
    severity === "critical" || severity === "high" ? "destructive" : severity === "medium" ? "warning" : "secondary";
  return <Badge variant={variant}>{optionLabel(severity)}</Badge>;
}

/**
 * What happened after confirmation: the processing run (polled while it is running) and the
 * alerts it raised on the new claim. Without a run id (a document confirmed earlier) it goes
 * straight to the claim's alerts.
 */
export function ConfirmResult({ claimId, runId }: { claimId: string; runId: number | null }) {
  const run = useRun(runId);
  const running = runId !== null && (run.isPending || run.data?.status === "running");
  const runFailed = run.data?.status === "failed";
  const alerts = useClaimAlerts(claimId, !running);

  const claimHref = `/claims/${encodeURIComponent(claimId)}`;

  return (
    <Panel aria-labelledby="result-title">
      <PanelHeader
        title={
          <span id="result-title" className="inline-flex items-center gap-2">
            <CircleCheck className="size-4 text-success" aria-hidden="true" />
            <span>
              Claim <span className="num">{claimId}</span> created
            </span>
          </span>
        }
        description="It passed the same checks as an imported row and is processed like any other claim."
      />
      <div className="space-y-4 p-4">
        {runId !== null && (
          <div className="flex items-start gap-3 rounded-lg border px-3 py-2.5" aria-live="polite">
            {running ? (
              <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin text-primary" aria-hidden="true" />
            ) : runFailed || run.isError ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
            ) : (
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
            )}
            <div className="min-w-0 text-[13px]">
              <p className="font-medium">
                {running
                  ? `Processing run #${runId}`
                  : run.isError
                    ? "Could not check the processing run"
                    : runFailed
                      ? `Processing run #${runId} failed`
                      : `Processing run #${runId} completed`}
              </p>
              <p className="mt-0.5 text-muted-foreground">
                {running
                  ? "Checking policy rules, duplicates and the settlement. This takes a few seconds."
                  : run.isError
                    ? getErrorMessage(run.error)
                    : runFailed
                      ? (run.data?.error ?? "The claim could not be processed.")
                      : "Every check ran on the claim."}
              </p>
            </div>
          </div>
        )}

        {!running && (
          <section aria-labelledby="alerts-title">
            <h3 id="alerts-title" className="text-[13px] font-semibold">
              Alerts on this claim
              {alerts.data && alerts.data.length > 0 && (
                <span className="num ml-1.5 font-normal text-muted-foreground">{formatNumber(alerts.data.length)}</span>
              )}
            </h3>
            {alerts.isPending ? (
              <div className="mt-2 space-y-2" aria-busy="true" aria-label="Loading alerts">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : alerts.isError ? (
              <p className="mt-1 text-[13px] text-muted-foreground">{getErrorMessage(alerts.error)}</p>
            ) : alerts.data.length === 0 ? (
              <p className="mt-1 flex items-center gap-1.5 text-[13px] text-muted-foreground">
                <ShieldCheck className="size-3.5 text-success" aria-hidden="true" />
                No alerts. The claim passed every check.
              </p>
            ) : (
              <ul className="mt-2 divide-y rounded-lg border">
                {alerts.data.map((alert) => (
                  <li key={alert.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                    <SeverityBadge severity={alert.severity} />
                    <span className="min-w-0 flex-1 text-[13px] font-medium">{alertCategoryLabel(alert.category)}</span>
                    {alert.amount !== null && (
                      <span className="num text-[13px]">
                        {formatINR(alert.amount)}{" "}
                        <span className="text-xs text-muted-foreground">{alert.amount_type}</span>
                      </span>
                    )}
                    <p className="basis-full text-xs text-pretty text-muted-foreground">{alert.explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button asChild>
            <Link href={claimHref}>
              Open claim
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/alerts">View all alerts</Link>
          </Button>
          <Button asChild variant="ghost">
            <Link href="/documents">Back to Documents</Link>
          </Button>
        </div>
      </div>
    </Panel>
  );
}
