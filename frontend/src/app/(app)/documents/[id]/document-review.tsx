"use client";

import { ArrowLeft, CircleAlert, FileWarning, LoaderCircle, SearchX, TriangleAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useDocument } from "@/lib/documents/hooks";
import {
  type ConfirmResult as ConfirmResultData,
  type DocumentDetail,
  type Extracted,
  isReading,
  isReviewable,
  readExtracted,
} from "@/lib/documents/model";
import { formatBytes, formatDateTime } from "@/lib/format";

import { ParseStatusBadge } from "../document-status";
import { ConfirmResult } from "./confirm-result";
import { DocumentPreview } from "./document-preview";
import { ReviewForm } from "./review-form";

function BackLink() {
  return (
    <Link
      href="/documents"
      className="mb-3 inline-flex items-center gap-1 rounded-sm text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="size-3.5" aria-hidden="true" />
      Documents
    </Link>
  );
}

export function DocumentReview({ id: rawId }: { id: string }) {
  const id = /^\d+$/.test(rawId) ? Number(rawId) : NaN;
  if (!Number.isSafeInteger(id) || id < 1) return <DocumentNotFound />;
  return <DocumentView id={id} />;
}

function DocumentNotFound() {
  return (
    <>
      <BackLink />
      <EmptyState
        icon={SearchX}
        title="Document not found"
        description="This document does not exist. It may have been removed when the demo data was reset."
        actions={
          <Button asChild variant="outline">
            <Link href="/documents">Back to Documents</Link>
          </Button>
        }
      />
    </>
  );
}

function routeLabel(extracted: Extracted): string | null {
  if (!extracted.route) return null;
  const how = extracted.route === "vision" ? "Read from the page images" : "Read from the text layer";
  return extracted.attempts && extracted.attempts > 1 ? `${how} in ${extracted.attempts} attempts` : how;
}

function DocumentView({ id }: { id: number }) {
  const doc = useDocument(id);
  // Kept here, not in the form: the form unmounts once the document turns confirmed.
  const [confirmed, setConfirmed] = useState<ConfirmResultData | null>(null);

  if (doc.isPending) return <DocumentReviewSkeleton />;
  if (doc.isError) {
    if (doc.error instanceof ApiError && doc.error.status === 404) return <DocumentNotFound />;
    return <LoadError message={getErrorMessage(doc.error)} onRetry={() => doc.refetch()} />;
  }

  const data = doc.data;
  const extracted = readExtracted(data.extracted);
  const route = routeLabel(extracted);
  const claimId = confirmed?.claim_id ?? data.claim_id;
  const status = confirmed ? "confirmed" : data.parse_status;

  return (
    <>
      <BackLink />
      <PageHeader
        title={
          <span className="inline-flex max-w-full flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className="min-w-0 break-all">{data.file_name}</span>
            <ParseStatusBadge status={status} />
          </span>
        }
        description={
          <>
            Uploaded <span className="num">{formatDateTime(data.created_at)}</span> ·{" "}
            <span className="num">{formatBytes(data.size_bytes)}</span>
            {route && <> · {route}</>}
          </>
        }
      />

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <DocumentPreview
          key={data.id}
          url={data.file_url}
          fileName={data.file_name}
          fileType={data.file_type}
          sizeBytes={data.size_bytes}
        />
        <div className="min-w-0 space-y-4">
          <ReviewBody
            data={data}
            extracted={extracted}
            status={status}
            claimId={claimId}
            runId={confirmed?.run.id ?? null}
            onConfirmed={setConfirmed}
          />
        </div>
      </div>
    </>
  );
}

function ReviewBody({
  data,
  extracted,
  status,
  claimId,
  runId,
  onConfirmed,
}: {
  data: DocumentDetail;
  extracted: Extracted;
  status: string;
  claimId: string | null;
  runId: number | null;
  onConfirmed: (result: ConfirmResultData) => void;
}) {
  const issues = data.issues ?? [];

  if (status === "confirmed" && claimId) return <ConfirmResult claimId={claimId} runId={runId} />;

  if (isReading(status)) {
    return (
      <Panel className="flex flex-col items-center px-6 py-12 text-center" aria-live="polite">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/8 text-primary ring-1 ring-primary/15 ring-inset">
          <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-base leading-6 font-semibold">Reading the invoice</h2>
        <p className="mt-1 max-w-sm text-sm text-pretty text-muted-foreground">
          The claim, provider and line items are being read and checked. This usually takes 10 to 40 seconds; the
          form appears here when it is done.
        </p>
        <ul className="mt-5 w-full max-w-xs space-y-2" aria-hidden="true">
          {[0.9, 0.7, 0.8].map((w, i) => (
            <li key={i}>
              <Skeleton className="h-3" style={{ width: `${w * 100}%` }} />
            </li>
          ))}
        </ul>
      </Panel>
    );
  }

  if (!isReviewable(status) || !extracted.draft) {
    return (
      <>
        <EmptyState
          icon={FileWarning}
          title="This document could not be read"
          description="No claim could be read from it. Check that it is a clear invoice, then upload it again or a better copy."
          actions={
            <Button asChild variant="outline">
              <Link href="/documents">
                <Upload data-icon="inline-start" aria-hidden="true" />
                Upload another document
              </Link>
            </Button>
          }
          className="py-10 sm:py-12"
        />
        {issues.length > 0 && <IssuesAlert issues={issues} failed />}
      </>
    );
  }

  return (
    <>
      {issues.length > 0 && <IssuesAlert issues={issues} needsReview={status === "needs_review"} />}
      <ReviewForm
        key={data.id}
        documentId={data.id}
        draft={extracted.draft}
        printedProviderName={extracted.printedProviderName}
        onConfirmed={onConfirmed}
      />
    </>
  );
}

function IssuesAlert({ issues, failed, needsReview }: { issues: string[]; failed?: boolean; needsReview?: boolean }) {
  if (failed) {
    return (
      <Alert variant="destructive">
        <CircleAlert aria-hidden="true" />
        <AlertTitle>What went wrong</AlertTitle>
        <AlertDescription>
          <IssueList issues={issues} />
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert className="border-warning/30 bg-warning/5 text-warning dark:bg-warning/10">
      <TriangleAlert aria-hidden="true" />
      <AlertTitle>
        {needsReview ? "Check these against the original before confirming" : "Worth a look before confirming"}
      </AlertTitle>
      <AlertDescription className="text-foreground/80">
        <IssueList issues={issues} />
      </AlertDescription>
    </Alert>
  );
}

function IssueList({ issues }: { issues: string[] }) {
  if (issues.length === 1) return <p className="break-words">{issues[0]}</p>;
  return (
    <ul className="list-disc space-y-0.5 pl-4">
      {issues.map((issue) => (
        <li key={issue} className="break-words">
          {issue}
        </li>
      ))}
    </ul>
  );
}

export function DocumentReviewSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading document">
      <Skeleton className="mb-3 h-4 w-20" />
      <div className="mb-5 space-y-2">
        <Skeleton className="h-7 w-64 max-w-full" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Skeleton className="h-[28rem] rounded-lg lg:h-[calc(100dvh-12rem)]" />
        <div className="space-y-4">
          <Skeleton className="h-64 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
      </div>
    </div>
  );
}
