"use client";

import { ArrowLeft, CircleAlert, CircleCheck, FileBraces, FileSpreadsheet, FileText, Play, SearchX, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { LoadError } from "@/components/app-shell/states";
import { RunStatus, RunValidationButton, useRunValidation } from "@/components/review/run-validation";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { useImportBatch } from "@/lib/imports/hooks";
import { type DatasetCounts, datasetLabel, type ImportBatch, isReconciled, sortDatasets } from "@/lib/imports/model";
import { useUrlState } from "@/lib/use-url-state";

import { BatchStatusBadge, OutcomeLegend, ReconciliationBar } from "../import-status";
import { ISSUE_URL_DEFAULTS, IssuesPanel } from "./issues-panel";

function BackLink() {
  return (
    <Link
      href="/imports"
      className="mb-3 inline-flex items-center gap-1 rounded-sm text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="size-3.5" aria-hidden="true" />
      Imports
    </Link>
  );
}

export function ImportDetail({ id: rawId }: { id: string }) {
  const id = /^\d+$/.test(rawId) ? Number(rawId) : NaN;
  if (!Number.isSafeInteger(id) || id < 1) return <ImportNotFound />;
  return <BatchView id={id} />;
}

function ImportNotFound() {
  return (
    <>
      <BackLink />
      <EmptyState
        icon={SearchX}
        title="Import not found"
        description="This import does not exist. It may have been removed when the demo data was reset."
        actions={
          <Button asChild variant="outline">
            <Link href="/imports">Back to Imports</Link>
          </Button>
        }
      />
    </>
  );
}

function BatchView({ id }: { id: number }) {
  const batch = useImportBatch(id);
  const [, setUrl] = useUrlState(ISSUE_URL_DEFAULTS);
  const validation = useRunValidation({ scope: "batch", batchId: id });

  if (batch.isPending) return <ImportDetailSkeleton />;
  if (batch.isError) {
    if (batch.error instanceof ApiError && batch.error.status === 404) return <ImportNotFound />;
    return <LoadError message={getErrorMessage(batch.error)} onRetry={() => batch.refetch()} />;
  }

  const data = batch.data;
  const datasets = sortDatasets(Object.keys(data.counts));

  const showIssues = (dataset: string) => {
    setUrl({ dataset, severity: "", page: "1" });
    document.getElementById("issues")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <BackLink />
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2.5">
            <span className="num">Import #{data.id}</span>
            <BatchStatusBadge status={data.status} />
          </span>
        }
        description={
          <>
            Uploaded <span className="num">{formatDateTime(data.uploaded_at)}</span> by {data.uploaded_by}
          </>
        }
        actions={<ValidateAction batch={data} isRunning={validation.isRunning} onRun={validation.startRun} />}
      />

      <div className="space-y-4">
        <RunStatus run={validation.run} onDismiss={validation.dismiss} />

        {data.error && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>This import failed</AlertTitle>
            <AlertDescription className="break-words">{data.error}</AlertDescription>
          </Alert>
        )}

        <FilesList batch={data} />

        <section aria-labelledby="reconciliation-title" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 id="reconciliation-title" className="text-sm font-semibold">
              Reconciliation
            </h2>
            {datasets.length > 0 && (
              <p className="text-[13px] text-muted-foreground">
                <span className="num font-medium text-foreground">{formatNumber(data.totals.received)}</span> rows
                received across {datasets.length === 1 ? "1 dataset" : `${formatNumber(datasets.length)} datasets`}
              </p>
            )}
          </div>
          {datasets.length === 0 ? (
            <Panel className="px-4 py-6 text-center text-sm text-muted-foreground">
              {data.error ? "No rows were read from these files." : "No rows were read from these files. The issues below explain why."}
            </Panel>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {datasets.map((dataset) => (
                <li key={dataset} className="min-w-0">
                  <DatasetCard dataset={dataset} counts={data.counts[dataset]} onShowIssues={showIssues} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <IssuesPanel batchId={data.id} datasets={datasets} failed={Boolean(data.error)} />
      </div>
    </>
  );
}

/** Claims from this batch that reached the database, so validation has something to check. */
function claimsAccepted(batch: ImportBatch): number {
  const claims = batch.counts.claims;
  return claims ? claims.accepted + claims.warnings : 0;
}

/** Runs validation on the claims from this import. Disabled, with the reason, when there are none. */
function ValidateAction({ batch, isRunning, onRun }: { batch: ImportBatch; isRunning: boolean; onRun: () => void }) {
  const reason =
    batch.status === "failed"
      ? "This import failed, so it has no claims to validate"
      : claimsAccepted(batch) === 0
        ? "No claims were accepted from this import"
        : null;
  if (!reason) return <RunValidationButton label="Run validation" isRunning={isRunning} onClick={onRun} />;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* A disabled button gets no pointer or focus events, so the wrapper carries the tooltip. */}
        <span tabIndex={0} className="inline-flex rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
          <Button disabled aria-disabled="true" tabIndex={-1}>
            <Play data-icon="inline-start" aria-hidden="true" />
            Run validation
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end">
        {reason}
      </TooltipContent>
    </Tooltip>
  );
}

function FileIcon({ name }: { name: string }) {
  const lower = name.toLowerCase();
  const Icon = lower.endsWith(".xlsx") ? FileSpreadsheet : lower.endsWith(".json") ? FileBraces : FileText;
  return <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />;
}

function FilesList({ batch }: { batch: ImportBatch }) {
  const count = batch.files.length;
  return (
    <Panel aria-labelledby="files-title">
      <div className="flex items-baseline justify-between gap-4 border-b px-4 py-2.5">
        <h2 id="files-title" className="text-sm font-semibold">
          {count === 1 ? "1 file" : `${formatNumber(count)} files`}
        </h2>
        <span className="num text-[13px] text-muted-foreground">
          {formatBytes(batch.files.reduce((sum, f) => sum + f.size, 0))}
        </span>
      </div>
      {count === 0 ? (
        <p className="px-4 py-3 text-sm text-muted-foreground">No files were stored for this import.</p>
      ) : (
        <ul className="divide-y">
          {batch.files.map((file, index) => (
            <li
              key={`${file.file_name}-${index}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2.5 sm:flex-nowrap"
            >
              <div className="flex min-w-0 flex-1 basis-full items-center gap-2.5 sm:basis-auto">
                <FileIcon name={file.file_name} />
                <span className="min-w-0 truncate text-sm font-medium" title={file.file_name}>
                  {file.file_name}
                </span>
                <span className="num shrink-0 text-[13px] text-muted-foreground">{formatBytes(file.size)}</span>
              </div>
              <ul aria-label={`Datasets in ${file.file_name}`} className="flex flex-wrap gap-1.5 pl-6.5 sm:pl-0">
                {file.datasets.length === 0 ? (
                  <li className="text-[13px] text-muted-foreground">No dataset recognised</li>
                ) : (
                  sortDatasets(file.datasets).map((d) => (
                    <li key={d}>
                      <Badge variant="outline" className="font-normal text-muted-foreground">
                        {datasetLabel(d)}
                      </Badge>
                    </li>
                  ))
                )}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DatasetCard({
  dataset,
  counts,
  onShowIssues,
}: {
  dataset: string;
  counts: DatasetCounts;
  onShowIssues: (dataset: string) => void;
}) {
  const reconciled = isReconciled(counts);
  const flagged = counts.warnings + counts.rejected;
  const label = datasetLabel(dataset);
  return (
    <Panel className="flex h-full flex-col p-4" aria-label={`${label} reconciliation`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[13px] font-medium text-muted-foreground">{label}</h3>
        {reconciled ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="-m-0.5 rounded-full p-0.5 text-success outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <CircleCheck className="size-4" aria-hidden="true" />
                <span className="sr-only">Reconciled</span>
              </span>
            </TooltipTrigger>
            <TooltipContent>Every received row is accounted for</TooltipContent>
          </Tooltip>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive">
            <TriangleAlert className="size-3.5" aria-hidden="true" />
            Does not add up
          </span>
        )}
      </div>
      <p className="mt-1.5 flex items-baseline gap-1.5">
        <span className="num text-2xl leading-8 font-semibold tracking-[-0.01em]">{formatNumber(counts.received)}</span>
        <span className="text-[13px] text-muted-foreground">received</span>
      </p>
      <ReconciliationBar counts={counts} className="mt-3" />
      <OutcomeLegend counts={counts} className="mt-3" />
      <div className="mt-auto pt-3">
        {flagged > 0 ? (
          <Button
            variant="link"
            size="sm"
            className="h-auto px-0 text-[13px]"
            onClick={() => onShowIssues(dataset)}
          >
            View issues
          </Button>
        ) : (
          <p className="text-[13px] text-muted-foreground">No issues</p>
        )}
      </div>
    </Panel>
  );
}

export function ImportDetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading import">
      <Skeleton className="mb-3 h-4 w-16" />
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
        <Skeleton className="h-8 w-32" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-40 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-80 w-full rounded-lg" />
      </div>
    </div>
  );
}
