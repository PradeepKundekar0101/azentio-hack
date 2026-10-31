"use client";

import { ArrowRight, CircleAlert, CircleCheck, LoaderCircle, Play, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { IndeterminateBar } from "@/components/indeterminate-bar";
import { Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { getErrorMessage } from "@/lib/api/errors";
import { formatDateTime, formatNumber } from "@/lib/format";
import {
  isRunInProgress,
  type Run,
  type RunScope,
  runningRunId,
  useLatestRun,
  useRun,
  useStartRun,
} from "@/lib/runs/hooks";
import { cn } from "@/lib/utils";

function sameScope(run: Run, scope: RunScope): boolean {
  return scope.scope === "all" ? run.scope === "all" : run.scope === "batch" && run.batch_id === scope.batchId;
}

/** "all claims" or "import #3". */
export function runScopeLabel(run: Pick<Run, "scope" | "batch_id">): string {
  return run.scope === "batch" && run.batch_id !== null ? `import #${run.batch_id}` : "all claims";
}

/**
 * Starts a validation run and follows it until it finishes. A run already in progress for the
 * same scope (for example after a reload) is picked up, and a 409 from the API (another run
 * is still going) follows that run instead of failing.
 */
export function useRunValidation(scope: RunScope) {
  const latest = useLatestRun();
  const start = useStartRun();
  const [runId, setRunId] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState<number | null>(null);

  const resumable =
    latest.data && latest.data.status === "running" && sameScope(latest.data, scope) ? latest.data.id : null;
  // Adopt the resumed run (during render, no effect) so its outcome stays on screen after it ends.
  if (runId === null && resumable !== null) setRunId(resumable);
  const run = useRun(runId ?? resumable);
  const current = run.data && run.data.id !== dismissed ? run.data : undefined;

  const startRun = () =>
    start.mutate(scope, {
      onSuccess: (created) => {
        setDismissed(null);
        setRunId(created.id);
      },
      onError: async (error) => {
        if (!isRunInProgress(error)) {
          toast.error(getErrorMessage(error));
          return;
        }
        const otherId = runningRunId(error) ?? (await latest.refetch()).data?.id ?? null;
        toast.info("Another validation run is still in progress. Its progress is shown here.");
        if (otherId !== null) {
          setDismissed(null);
          setRunId(otherId);
        }
      },
    });

  return {
    run: current,
    isRunning: start.isPending || current?.status === "running",
    isStarting: start.isPending,
    startRun,
    dismiss: () => setDismissed(current?.id ?? null),
  };
}

export function RunValidationButton({
  label,
  isRunning,
  onClick,
  variant = "default",
}: {
  label: string;
  isRunning: boolean;
  onClick: () => void;
  variant?: "default" | "outline";
}) {
  return (
    <Button variant={variant} onClick={onClick} disabled={isRunning} aria-busy={isRunning || undefined}>
      {isRunning ? (
        <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />
      ) : (
        <Play data-icon="inline-start" aria-hidden="true" />
      )}
      {isRunning ? "Validating" : label}
    </Button>
  );
}

/**
 * Where a run stands: progress while it runs, then the outcome with links to the results.
 * Announced politely so screen readers hear when it finishes.
 */
export function RunStatus({
  run,
  onDismiss,
  showDashboardLink = true,
  className,
}: {
  run: Run | undefined;
  onDismiss: () => void;
  showDashboardLink?: boolean;
  className?: string;
}) {
  if (!run) return null;
  const scope = runScopeLabel(run);

  if (run.status === "running") {
    return (
      <Panel className={cn("space-y-2 px-4 py-3", className)} aria-live="polite">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[13px]">
          <span className="font-medium">Validating {scope}</span>
          <span className="num text-muted-foreground">Started {formatDateTime(run.started_at)}</span>
        </div>
        <IndeterminateBar label={`Validating ${scope}`} />
        <p className="text-xs text-muted-foreground">
          Every claim is checked against its policy and compared with earlier claims. This usually takes a few seconds.
        </p>
      </Panel>
    );
  }

  const failed = run.status === "failed";
  const partial = !failed && run.claims_failed > 0;
  const Icon = failed ? CircleAlert : partial ? TriangleAlert : CircleCheck;

  return (
    <Panel
      aria-live="polite"
      className={cn("relative px-4 py-3 pr-12", failed && "border-destructive/25 bg-destructive/5", className)}
    >
      <div className="flex items-start gap-2.5">
        <Icon
          className={cn(
            "mt-0.5 size-4 shrink-0",
            failed ? "text-destructive" : partial ? "text-warning" : "text-success",
          )}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1 space-y-1">
          <p className={cn("text-sm font-medium", failed && "text-destructive")}>
            {failed ? `Validation of ${scope} failed` : `Validated ${scope}`}
          </p>
          {failed ? (
            <p className="text-[13px] break-words text-destructive/90">
              {run.error ?? "The run stopped before it finished. Try again."}
            </p>
          ) : (
            <p className="num text-[13px] text-muted-foreground">
              <span className="font-medium text-foreground">{formatNumber(run.claims_processed)}</span>{" "}
              {run.claims_processed === 1 ? "claim" : "claims"} processed
              {run.claims_failed > 0 && (
                <>
                  {" · "}
                  <span className="font-medium text-warning">{formatNumber(run.claims_failed)}</span> could not be
                  processed
                </>
              )}
              {run.finished_at && <> · finished {formatDateTime(run.finished_at)}</>}
            </p>
          )}
          {run.failures && run.failures.length > 0 && (
            <ul className="mt-1.5 space-y-0.5 text-[13px]">
              {run.failures.slice(0, 5).map((f) => (
                <li key={f.claim_id} className="flex min-w-0 gap-2">
                  <span className="num shrink-0 font-medium">{f.claim_id}</span>
                  <span className="min-w-0 truncate text-muted-foreground" title={f.error}>
                    {f.error}
                  </span>
                </li>
              ))}
              {run.failures.length > 5 && (
                <li className="text-xs text-muted-foreground">and {formatNumber(run.failures.length - 5)} more</li>
              )}
            </ul>
          )}
          {!failed && (
            <div className="flex flex-wrap gap-2 pt-1.5">
              {showDashboardLink && (
                <Button asChild size="sm">
                  <Link href="/">
                    Open dashboard
                    <ArrowRight data-icon="inline-end" aria-hidden="true" />
                  </Link>
                </Button>
              )}
              <Button asChild size="sm" variant={showDashboardLink ? "outline" : "default"}>
                <Link href="/alerts">
                  View alerts
                  <ArrowRight data-icon="inline-end" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute top-2 right-2 text-muted-foreground"
        aria-label="Dismiss"
        onClick={onDismiss}
      >
        <X aria-hidden="true" />
      </Button>
    </Panel>
  );
}
