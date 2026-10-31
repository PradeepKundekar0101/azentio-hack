"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileJson, FileText, FolderOpen, LoaderCircle, ScrollText, SearchX } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { claimTypeLabel } from "@/lib/alerts/model";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { evidenceKeys, useInvestigation, useOpenInvestigation } from "@/lib/evidence/hooks";
import { type Investigation, reportUrl } from "@/lib/evidence/model";
import { formatDate, formatINR } from "@/lib/format";

import { FindingsPanel, OriginalCalculation } from "./findings";
import { IntegritySeal, SummaryTiles } from "./integrity";
import { EvidenceTimeline } from "./timeline";

const CLAIM_ID_RE = /^[A-Za-z0-9-]{1,40}$/;

function BackLink({ claimId }: { claimId: string }) {
  return (
    <Link
      href={`/claims/${encodeURIComponent(claimId)}`}
      className="mb-3 inline-flex items-center gap-1 rounded-sm text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="size-3.5" aria-hidden="true" />
      Claim <span className="num">{claimId}</span>
    </Link>
  );
}

function NotFound() {
  return (
    <EmptyState
      icon={SearchX}
      title="Claim not found"
      description="No claim has this ID, so there is no evidence to show."
      actions={
        <Button asChild variant="outline">
          <Link href="/evidence">Back to Evidence</Link>
        </Button>
      }
    />
  );
}

function Downloads({ claimId, enabled }: { claimId: string; enabled: boolean }) {
  const queryClient = useQueryClient();
  // The backend records every download in the history; refresh shortly after so the entry appears.
  const recorded = () =>
    window.setTimeout(() => void queryClient.invalidateQueries({ queryKey: evidenceKeys.claim(claimId) }), 1200);
  if (!enabled) return null;
  return (
    <>
      <Button asChild variant="outline">
        <a href={reportUrl(claimId, "json")} download onClick={recorded}>
          <FileJson data-icon="inline-start" aria-hidden="true" />
          JSON
        </a>
      </Button>
      <Button asChild>
        <a href={reportUrl(claimId, "pdf")} download onClick={recorded}>
          <FileText data-icon="inline-start" aria-hidden="true" />
          Download report
        </a>
      </Button>
    </>
  );
}

function NotOpened({ data }: { data: Investigation }) {
  const open = useOpenInvestigation(data.claim.claim_id);
  return (
    <EmptyState
      icon={ScrollText}
      title="No investigation yet"
      description={
        data.findings.length > 0
          ? `This claim has ${data.findings.length} finding(s). Opening the investigation freezes the original calculation, the detected issues and the recommended corrections, so every later change is measured against them. It also opens automatically on the first decision, override or note.`
          : "Opening the investigation freezes the current calculation as the baseline. It also opens automatically on the first decision, override or note."
      }
      actions={
        <Button
          disabled={open.isPending}
          onClick={() =>
            open.mutate(undefined, {
              onSuccess: () => toast.success("Investigation opened. The original calculation is frozen."),
              onError: (error) => toast.error(getErrorMessage(error)),
            })
          }
        >
          {open.isPending ? (
            <LoaderCircle className="animate-spin" data-icon="inline-start" aria-hidden="true" />
          ) : (
            <FolderOpen data-icon="inline-start" aria-hidden="true" />
          )}
          Open investigation
        </Button>
      }
    />
  );
}

export function EvidenceView({ id: rawId }: { id: string }) {
  const id = decodeURIComponent(rawId);
  if (!CLAIM_ID_RE.test(id)) return <NotFound />;
  return <Evidence claimId={id} />;
}

function Evidence({ claimId }: { claimId: string }) {
  const query = useInvestigation(claimId);
  if (query.isPending) return <EvidenceSkeleton />;
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <NotFound />;
    return <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  }
  const data = query.data;
  const { claim } = data;

  return (
    <>
      <BackLink claimId={claimId} />
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-baseline gap-2">
            Evidence trail <span className="num text-muted-foreground">· {claim.claim_id}</span>
          </span>
        }
        description={
          <>
            {claim.claimant_name} · {claimTypeLabel(claim.claim_type)} · policy{" "}
            <span className="num">{claim.policy_number}</span> · incident{" "}
            <span className="num">{formatDate(claim.incident_date)}</span> · requested{" "}
            <span className="num">{formatINR(claim.requested_amount)}</span>
          </>
        }
        actions={<Downloads claimId={claimId} enabled={data.investigation !== null} />}
      />

      {data.investigation === null ? (
        <NotOpened data={data} />
      ) : (
        <div className="space-y-4">
          <IntegritySeal data={data} />
          <SummaryTiles data={data} />
          <div className="grid items-start gap-4 xl:grid-cols-5">
            <div className="min-w-0 space-y-4 xl:col-span-3">
              <FindingsPanel data={data} />
              <OriginalCalculation data={data} />
            </div>
            <div className="min-w-0 xl:col-span-2">
              <EvidenceTimeline data={data} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function EvidenceSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading evidence">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="h-7 w-80" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-4 xl:grid-cols-5">
        <Skeleton className="h-96 xl:col-span-3" />
        <Skeleton className="h-96 xl:col-span-2" />
      </div>
    </div>
  );
}
