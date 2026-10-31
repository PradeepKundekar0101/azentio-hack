"use client";

import { FileSearch, Sparkles } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { Panel, PanelHeader } from "@/components/page";
import { AlertAmount } from "@/components/review/badges";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api/errors";
import { useClaim } from "@/lib/claims/hooks";
import {
  type ClaimLine,
  type ComparisonOut,
  comparisonRows,
  discrepancyLabel,
  type DiscrepancyOut,
  headerRows,
  type LineRow,
  type Target,
} from "@/lib/documents/comparison";
import { documentContentUrl, useDocumentComparison, useExtraction } from "@/lib/documents/comparison-hooks";
import { EMPTY, formatDate, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

const DocumentViewer = dynamic(() => import("./document-viewer").then((m) => m.DocumentViewer), {
  ssr: false,
  loading: () => <Skeleton className="aspect-[1/1.414] w-full" />,
});

const DOC_TYPE_LABELS: Record<string, string> = {
  invoice: "Invoice",
  discharge_summary: "Discharge summary",
  repair_estimate: "Repair estimate",
};

function ProvenanceMark({ status }: { status: string | null }) {
  if (!status) return null;
  const label = { verified: "Found on the page", page_only: "Read from the image", unverified: "Not found on the page" }[status];
  return (
    <span
      title={label}
      className={cn(
        "ml-1 inline-block size-1.5 rounded-full align-middle",
        status === "verified" ? "bg-success" : status === "page_only" ? "bg-warning" : "bg-destructive",
      )}
    />
  );
}

function headerValue(key: string, value: string | null): string {
  if (value === null) return EMPTY;
  if (key === "total") return formatINR(value);
  if (key.endsWith("_date")) return formatDate(value);
  return value;
}

function Cell({ value, differs, className }: { value: React.ReactNode; differs?: boolean; className?: string }) {
  return (
    <td
      className={cn(
        "num px-2 py-1.5 align-top whitespace-nowrap",
        differs && "bg-destructive/8 font-semibold text-destructive",
        className,
      )}
    >
      {value}
    </td>
  );
}

function LinesTable({ rows, selected, onSelect }: { rows: LineRow[]; selected: string | null; onSelect: (row: LineRow) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-[13px]">
        <thead className="text-[11px] tracking-wide text-muted-foreground uppercase">
          <tr className="border-b">
            <th className="px-2 py-1.5 text-left font-medium" colSpan={3}>
              Claim
            </th>
            <th className="border-l px-2 py-1.5 text-left font-medium" colSpan={3}>
              Document
            </th>
          </tr>
          <tr className="border-b">
            <th className="px-2 py-1 text-left font-medium">Line</th>
            <th className="px-2 py-1 text-right font-medium">Qty × rate</th>
            <th className="px-2 py-1 text-right font-medium">Amount</th>
            <th className="border-l px-2 py-1 text-left font-medium">Line</th>
            <th className="px-2 py-1 text-right font-medium">Qty × rate</th>
            <th className="px-2 py-1 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const flagged = row.discrepancies.some((d) => d.amount_impact != null) || row.kind === "claim_only";
            return (
              <tr
                key={row.key}
                onClick={() => onSelect(row)}
                className={cn(
                  "cursor-pointer border-b last:border-b-0 hover:bg-muted/50",
                  selected === row.key && "bg-primary/6",
                  flagged && "border-l-2 border-l-destructive",
                )}
              >
                {row.claim ? (
                  <>
                    <td className="px-2 py-1.5 align-top">
                      <div className="font-medium">{row.claim.service_description}</div>
                      <div className="num text-[11px] text-muted-foreground">
                        {row.claim.line_id} · {formatDate(row.claim.service_date)}
                      </div>
                    </td>
                    <Cell
                      className="text-right"
                      value={`${Number(row.claim.quantity)} × ${formatINR(row.claim.unit_price)}`}
                      differs={row.differs.includes("quantity") || row.differs.includes("unit_price")}
                    />
                    <Cell className="text-right" value={formatINR(row.claim.line_amount)} differs={row.differs.includes("amount")} />
                  </>
                ) : (
                  <td colSpan={3} className="px-2 py-1.5 text-[12px] text-muted-foreground italic">
                    Not claimed
                  </td>
                )}
                {row.doc ? (
                  <>
                    <td className="border-l px-2 py-1.5 align-top">
                      <div className="font-medium">
                        {row.doc.description}
                        {row.aiMatch && (
                          <Badge variant="outline" className="ml-1.5 gap-1" title="Matched by the model, not by rule">
                            <Sparkles aria-hidden="true" /> AI-suggested match
                          </Badge>
                        )}
                      </div>
                      <div className={cn("num text-[11px] text-muted-foreground", row.differs.includes("service_date") && "font-semibold text-destructive")}>
                        Line {row.doc.line_no} · {formatDate(row.doc.service_date)}
                      </div>
                    </td>
                    <Cell
                      className="text-right"
                      value={`${Number(row.doc.quantity)} × ${formatINR(row.doc.unit_price)}`}
                      differs={row.differs.includes("quantity") || row.differs.includes("unit_price")}
                    />
                    <Cell className="text-right" value={formatINR(row.doc.amount)} differs={row.differs.includes("amount")} />
                  </>
                ) : (
                  <td colSpan={3} className="border-l px-2 py-1.5 text-[12px] font-medium text-destructive">
                    Not on the invoice
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DiscrepancyList({ items, onSelect }: { items: DiscrepancyOut[]; onSelect: (d: DiscrepancyOut) => void }) {
  if (items.length === 0) {
    return <p className="px-4 py-3 text-[13px] text-muted-foreground">No differences between this document and the claim.</p>;
  }
  const ordered = [...items].sort((a, b) => Number(b.amount_impact ?? -1) - Number(a.amount_impact ?? -1));
  return (
    <ul className="divide-y">
      {ordered.map((d) => (
        <li key={d.discrepancy_id}>
          <button type="button" onClick={() => onSelect(d)} className="w-full px-4 py-2.5 text-left hover:bg-muted/50">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold">{discrepancyLabel(d.type)}</span>
              {d.generated_by === "ai" && (
                <Badge variant="outline" className="gap-1" title={`Assessed by ${d.model}`}>
                  <Sparkles aria-hidden="true" /> AI
                </Badge>
              )}
              <span className="ml-auto">
                {d.amount_impact != null ? (
                  <AlertAmount amount={d.amount_impact} type={d.amount_type ?? "estimated"} />
                ) : (
                  <span className="text-[12px] text-muted-foreground">No amount</span>
                )}
              </span>
            </div>
            <p className="mt-0.5 text-[12px] text-pretty text-muted-foreground">{d.explanation}</p>
            <p className="num mt-0.5 text-[11px] text-muted-foreground">{d.discrepancy_id}</p>
          </button>
        </li>
      ))}
    </ul>
  );
}

function ComparisonBody({ comparison, claim, lines }: { comparison: ComparisonOut; claim: { claimant_name: string; incident_date: string }; lines: ClaimLine[] }) {
  const extraction = useExtraction(comparison.document.id, comparison.extraction_version);
  const [selected, setSelected] = useState<{ key: string; target: Target | null } | null>(null);
  const rows = useMemo(
    () => (extraction.data ? comparisonRows(comparison, lines, extraction.data) : []),
    [comparison, lines, extraction.data],
  );
  if (extraction.isPending) return <Skeleton className="m-4 h-64" />;
  if (extraction.isError) return <LoadError message={getErrorMessage(extraction.error)} onRetry={() => extraction.refetch()} />;
  const header = headerRows(extraction.data, claim, lines);
  const select = (key: string, target: Target | null) => setSelected({ key, target });
  return (
    <div className="grid xl:grid-cols-5">
      <div className="min-w-0 space-y-0 border-b xl:col-span-3 xl:border-r xl:border-b-0">
        <table className="w-full text-[13px]">
          <thead className="text-[11px] tracking-wide text-muted-foreground uppercase">
            <tr className="border-b">
              <th className="px-4 py-1.5 text-left font-medium">Field</th>
              <th className="px-2 py-1.5 text-left font-medium">Claim</th>
              <th className="px-2 py-1.5 text-left font-medium">Document</th>
            </tr>
          </thead>
          <tbody>
            {header.map((row) => (
              <tr
                key={row.key}
                onClick={() => select(`header:${row.key}`, row.target)}
                className={cn("cursor-pointer border-b hover:bg-muted/50", selected?.key === `header:${row.key}` && "bg-primary/6")}
              >
                <td className="px-4 py-1.5 text-muted-foreground">{row.label}</td>
                <Cell value={headerValue(row.key, row.claimValue)} differs={row.differs} />
                <Cell
                  value={
                    <>
                      {headerValue(row.key, row.documentValue)}
                      <ProvenanceMark status={row.provenance} />
                    </>
                  }
                  differs={row.differs}
                />
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 0 && (
          <div className="border-b">
            <LinesTable rows={rows} selected={selected?.key ?? null} onSelect={(row) => select(row.key, row.target)} />
          </div>
        )}
        <div>
          <h3 className="px-4 pt-3 text-[12px] font-semibold">
            Discrepancies <span className="num font-normal text-muted-foreground">({comparison.discrepancies.length})</span>
          </h3>
          <DiscrepancyList
            items={comparison.discrepancies}
            onSelect={(d) => {
              const ref = d.document_ref as { page?: number; bbox?: Target["bbox"] };
              select(d.discrepancy_id, ref.page ? { page: ref.page, bbox: ref.bbox ?? null } : null);
            }}
          />
        </div>
      </div>
      <aside className="bg-muted/30 p-4 xl:col-span-2">
        <div className="xl:sticky xl:top-4">
          <div className="mb-2 flex items-center justify-between gap-2 text-[12px] text-muted-foreground">
            <span className="truncate">{comparison.document.file_name}</span>
            <span>{selected?.target?.bbox ? "Highlighted where it was printed" : "Select a value to see where it was printed"}</span>
          </div>
          <DocumentViewer
            url={documentContentUrl(comparison.document.id)}
            fileType={comparison.document.file_type}
            target={selected?.target ?? null}
          />
        </div>
      </aside>
    </div>
  );
}

/**
 * The claim's values beside each supporting document's, the differences found, and the document itself with the
 * selected value highlighted. Takes the claim ID; no routing or auth logic, so any page can embed it.
 */
export function DocumentComparison({ claimId }: { claimId: string }) {
  const query = useDocumentComparison(claimId);
  const claim = useClaim(claimId);
  const [active, setActive] = useState(0);
  const comparisons = query.data?.comparisons ?? [];
  const current = comparisons[Math.min(active, comparisons.length - 1)];
  return (
    <Panel>
      <PanelHeader
        title="Documents"
        description="Invoices and discharge summaries compared with the claim, line by line."
        actions={
          query.data && (query.data.totals.calculated !== "0" || query.data.totals.estimated !== "0") ? (
            <div className="flex items-center gap-2 text-[12px]">
              <AlertAmount amount={query.data.totals.calculated} type="calculated" />
              {Number(query.data.totals.estimated) > 0 && <AlertAmount amount={query.data.totals.estimated} type="estimated" />}
            </div>
          ) : undefined
        }
      />
      {(query.isPending || claim.isPending) && <Skeleton className="m-4 h-64" />}
      {query.isError && <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />}
      {query.data && claim.data && comparisons.length === 0 && (
        <EmptyState icon={FileSearch} title="No documents compared yet" description="Upload an invoice or a discharge summary for this claim." />
      )}
      {query.data && claim.data && current && (
        <>
          <div role="tablist" aria-label="Documents" className="flex gap-1 overflow-x-auto border-b px-3 pt-2">
            {comparisons.map((c, index) => (
              <button
                key={c.comparison_id}
                type="button"
                role="tab"
                aria-selected={c === current}
                onClick={() => setActive(index)}
                className={cn(
                  "-mb-px flex items-center gap-2 rounded-t-md border border-transparent px-3 py-1.5 text-[13px] whitespace-nowrap",
                  c === current ? "border-border border-b-card bg-card font-medium" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {DOC_TYPE_LABELS[c.doc_type] ?? c.doc_type}
                <span className="num text-[11px] text-muted-foreground">{c.document.file_name}</span>
                {c.discrepancies.length > 0 && (
                  <Badge variant="destructive" className="num">
                    {c.discrepancies.length}
                  </Badge>
                )}
              </button>
            ))}
          </div>
          <ComparisonBody key={current.comparison_id} comparison={current} claim={claim.data.claim} lines={claim.data.lines} />
        </>
      )}
    </Panel>
  );
}
