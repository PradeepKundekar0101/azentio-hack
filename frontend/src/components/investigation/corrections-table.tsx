"use client";

import { Calculator, CheckCircle2, RefreshCw, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { Panel, PanelHeader } from "@/components/page";
import { AmountTypeBadge } from "@/components/review/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useCorrections, useCorrectionVersions, useRecompute } from "@/lib/corrections/hooks";
import {
  correctionLabel,
  type CorrectionOut,
  type CorrectionSetOut,
  evidenceKind,
  reconciles,
  settlementSummary,
  splitCorrections,
} from "@/lib/corrections/model";
import { formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

function Chips({ correction }: { correction: CorrectionOut }) {
  return (
    <div className="flex flex-wrap gap-1">
      {correction.policy_rule_id && (
        <Badge variant="outline" className="num" title="Policy rule">
          {correction.policy_rule_id}
        </Badge>
      )}
      {correction.evidence_refs.map((ref) => (
        <Badge key={ref} variant="secondary" className="num" title={evidenceKind(ref)}>
          {ref}
        </Badge>
      ))}
    </div>
  );
}

function Row({ correction, muted }: { correction: CorrectionOut; muted?: boolean }) {
  return (
    <tr className={cn("border-b align-top last:border-b-0", muted && "text-muted-foreground")}>
      <td className="num px-3 py-2 text-[12px] text-muted-foreground">{correction.sequence}</td>
      <td className="px-3 py-2">
        <div className="text-[13px] font-medium text-foreground">{correctionLabel(correction.type)}</div>
        {correction.line_id && <div className="num text-[11px] text-muted-foreground">{correction.line_id}</div>}
      </td>
      <td className="max-w-[360px] px-3 py-2 text-[12px] text-pretty">
        <div className="num">{correction.calculation_text}</div>
        <div className="mt-1">
          <Chips correction={correction} />
        </div>
      </td>
      <td className="num px-3 py-2 text-right text-[13px] whitespace-nowrap">{formatINR(correction.original_amount)}</td>
      <td className="num px-3 py-2 text-right text-[13px] whitespace-nowrap">{formatINR(correction.corrected_amount)}</td>
      <td className="num px-3 py-2 text-right text-[13px] font-semibold whitespace-nowrap text-destructive">
        {correction.difference === "0.00" ? formatINR(0) : `−${formatINR(correction.difference)}`}
      </td>
    </tr>
  );
}

function Summary({ set }: { set: CorrectionSetOut }) {
  const parts = settlementSummary(set);
  const items = [
    { label: "Not supported by the documents", hint: "missing from the invoice, billed higher, extra room days, repeats", value: parts.documents, tone: "text-destructive" },
    { label: "Above the policy's limits", hint: "sub-limits, exclusions, overall limit", value: parts.policyLimits, tone: "text-destructive" },
    { label: "Normal policy terms", hint: "deductible and co-pay", value: parts.policyTerms, tone: "text-muted-foreground" },
  ];
  return (
    <div className="border-b px-4 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[13px] text-muted-foreground">Claimed</span>
        <span className="num text-lg font-semibold">{formatINR(set.requested_amount)}</span>
        <span className="text-muted-foreground" aria-hidden="true">→</span>
        <span className="text-[13px] text-muted-foreground">Pay</span>
        <span className="num text-lg font-semibold text-success">{formatINR(set.recommended_payable)}</span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {items.map((item) => (
          <div key={item.label} className="rounded-md border bg-muted/30 px-3 py-2">
            <div className={cn("num text-[15px] font-semibold", item.tone)}>
              {item.value === "0.00" ? formatINR(0) : `−${formatINR(item.value)}`}
            </div>
            <div className="text-[12px] font-medium">{item.label}</div>
            <div className="text-[11px] text-muted-foreground">{item.hint}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[12px] text-muted-foreground">
        The steps below apply these in order, each starting from the previous one&apos;s result, so nothing is counted twice.
      </p>
    </div>
  );
}

function Table({ set }: { set: CorrectionSetOut }) {
  const { applied, review, recovery } = splitCorrections(set);
  const ok = reconciles(set);
  return (
    <>
      <Summary set={set} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <thead className="text-[11px] tracking-wide text-muted-foreground uppercase">
            <tr className="border-b">
              <th className="w-8 px-3 py-2 text-left font-medium">#</th>
              <th className="px-3 py-2 text-left font-medium">Correction</th>
              <th className="px-3 py-2 text-left font-medium">Calculation and support</th>
              <th className="px-3 py-2 text-right font-medium">Before</th>
              <th className="px-3 py-2 text-right font-medium">After</th>
              <th className="px-3 py-2 text-right font-medium">Difference</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b bg-muted/40">
              <td />
              <td className="px-3 py-2 text-[13px] font-semibold" colSpan={4}>
                Requested
              </td>
              <td className="num px-3 py-2 text-right text-[13px] font-semibold">{formatINR(set.requested_amount)}</td>
            </tr>
            {applied.map((c) => (
              <Row key={c.correction_id} correction={c} />
            ))}
            <tr className="border-t-2 bg-muted/40">
              <td />
              <td className="px-3 py-2.5 text-[13px] font-semibold" colSpan={4}>
                Recommended payable
                <span className={cn("ml-2 inline-flex items-center gap-1 text-[12px] font-normal", ok ? "text-success" : "text-destructive")}>
                  {ok ? <CheckCircle2 className="size-3.5" aria-hidden="true" /> : <TriangleAlert className="size-3.5" aria-hidden="true" />}
                  {ok ? "Reconciles: requested − corrections" : "Does not reconcile"}
                </span>
              </td>
              <td className="num px-3 py-2.5 text-right text-[15px] font-semibold">{formatINR(set.recommended_payable)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {recovery && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t bg-destructive/5 px-4 py-3">
          <div>
            <div className="text-[13px] font-semibold">Recover overpayment</div>
            <div className="num text-[12px] text-muted-foreground">{recovery.calculation_text}</div>
          </div>
          <span className="num text-[15px] font-semibold text-destructive">{formatINR(recovery.difference)}</span>
        </div>
      )}
      {review.length > 0 && (
        <div className="border-t">
          <h3 className="flex items-center gap-2 px-4 pt-3 text-[12px] font-semibold">
            For review <span className="font-normal text-muted-foreground">(estimates, not applied to the payable)</span>
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <tbody>
                {review.map((c) => (
                  <tr key={c.correction_id} className="border-b align-top last:border-b-0">
                    <td className="px-3 py-2">
                      <div className="text-[13px] font-medium">{correctionLabel(c.type)}</div>
                      {c.line_id && <div className="num text-[11px] text-muted-foreground">{c.line_id}</div>}
                    </td>
                    <td className="max-w-[420px] px-3 py-2 text-[12px] text-pretty text-muted-foreground">
                      {c.explanation}
                      <div className="mt-1">
                        <Chips correction={c} />
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <AmountTypeBadge type={c.amount_type} />
                    </td>
                    <td className="num px-3 py-2 text-right text-[13px] whitespace-nowrap">−{formatINR(c.difference)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

/**
 * The recommended settlement for a claim: requested amount, each correction with its calculation and the rule or
 * evidence behind it, the recommended payable, items for review, and earlier versions. No routing or auth logic.
 */
export function CorrectionsTable({ claimId }: { claimId: string }) {
  const [version, setVersion] = useState<number | null>(null);
  const query = useCorrections(claimId, version);
  const versions = useCorrectionVersions(claimId);
  const recompute = useRecompute(claimId);
  const missing = query.error instanceof ApiError && query.error.status === 404;
  return (
    <Panel>
      <PanelHeader
        title="Recommended settlement"
        description="Specific corrections from the requested amount to the amount payable, in the order applied."
        actions={
          <div className="flex items-center gap-2">
            {versions.data && versions.data.length > 1 && (
              <select
                aria-label="Version"
                className="h-8 rounded-md border bg-background px-2 text-[13px]"
                value={version ?? ""}
                onChange={(e) => setVersion(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Latest (v{versions.data.at(-1)?.version})</option>
                {versions.data.map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version} · {formatDateTime(v.created_at)} · {formatINR(v.recommended_payable)}
                  </option>
                ))}
              </select>
            )}
            <Button variant="outline" size="sm" onClick={() => recompute.mutate()} disabled={recompute.isPending}>
              <RefreshCw data-icon="inline-start" aria-hidden="true" className={cn(recompute.isPending && "animate-spin")} />
              Recompute
            </Button>
          </div>
        }
      />
      {query.isPending && <Skeleton className="m-4 h-64" />}
      {missing && (
        <EmptyState
          icon={Calculator}
          title="No corrections yet"
          description="Nothing was found on this claim. Recompute to build its settlement anyway."
        />
      )}
      {query.isError && !missing && <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />}
      {query.data && <Table set={query.data} />}
    </Panel>
  );
}
