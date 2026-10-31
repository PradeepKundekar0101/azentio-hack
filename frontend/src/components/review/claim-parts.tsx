"use client";

import { ArrowRight, ChevronRight, FileText } from "lucide-react";
import Link from "next/link";

import { Panel, PanelHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { checkName, claimTypeLabel } from "@/lib/alerts/model";
import {
  basisLabel,
  type CheckGroup,
  type ClaimDetail,
  type ClaimOut,
  describeSignals,
  formatScore,
  groupResults,
  type LineOut,
  type MatchOut,
  matchTypeLabel,
  outcomeTotals,
  type PolicyOut,
  type PolicyRuleOut,
  type ResultOut,
  ruleTypeLabel,
  type SettlementOut,
  type SourceRow,
  sourceRowLabel,
  type StepOut,
} from "@/lib/claims/model";
import { EMPTY, formatDate, formatINR, formatNumber, formatPercent, toPaise } from "@/lib/format";
import { cn } from "@/lib/utils";

import { OutcomeBadge } from "./badges";

export const linkClass =
  "rounded-sm font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring";

export function ClaimLink({ id, className }: { id: string; className?: string }) {
  return (
    <Link href={`/claims/${encodeURIComponent(id)}`} className={cn(linkClass, className)}>
      <span className="num">{id}</span>
    </Link>
  );
}

/** Where a record came from: file, sheet and row. */
export function SourceRowText({ source, className }: { source: SourceRow | null | undefined; className?: string }) {
  const label = sourceRowLabel(source);
  if (!label) return <span className={cn("text-xs text-muted-foreground", className)}>Source not recorded</span>;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1 text-xs text-muted-foreground", className)}>
      <FileText className="size-3 shrink-0" aria-hidden="true" />
      <span className="num min-w-0 truncate" title={label}>
        {label}
      </span>
    </span>
  );
}

export function ClaimStatusBadge({ status }: { status: string }) {
  if (status === "settled") return <Badge variant="secondary">Settled</Badge>;
  if (status === "open") return <Badge variant="outline">Open</Badge>;
  return <Badge variant="secondary">{basisLabel(status)}</Badge>;
}

/** Definition rows in a two-column grid that collapses to one column on phones. */
export function Facts({
  items,
  className,
}: {
  items: { label: string; value: React.ReactNode; highlight?: boolean; wide?: boolean }[];
  className?: string;
}) {
  return (
    <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-2", className)}>
      {items.map((item) => (
        <div key={item.label} className={cn("min-w-0", item.wide && "sm:col-span-2")}>
          <dt className="text-xs text-muted-foreground">{item.label}</dt>
          <dd className="mt-0.5 min-w-0 font-medium break-words">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function claimFacts(claim: ClaimOut) {
  return [
    { label: "Claimant", value: `${claim.claimant_name} (${claim.claimant_id})` },
    { label: "Policy", value: <span className="num">{claim.policy_number}</span> },
    { label: "Claim type", value: claimTypeLabel(claim.claim_type) },
    { label: "Incident date", value: <span className="num">{formatDate(claim.incident_date)}</span> },
    { label: "Submitted", value: <span className="num">{formatDate(claim.submission_date)}</span> },
    { label: "Incident reference", value: claim.incident_reference ?? EMPTY },
    { label: "Requested", value: <span className="num">{formatINR(claim.requested_amount)}</span> },
    {
      label: "Payable after policy terms",
      value: <span className="num">{claim.payable == null ? EMPTY : formatINR(claim.payable)}</span>,
    },
    { label: "Source row", value: <SourceRowText source={claim.source_row} className="text-[13px]" />, wide: true },
  ];
}

/**
 * All lines of a claim. Lines the alert points at are highlighted, and marked in words so
 * the highlight is not colour alone.
 */
export function LinesTable({
  lines,
  flagged = new Set<string>(),
  original = new Set<string>(),
  caption,
}: {
  lines: readonly LineOut[];
  flagged?: ReadonlySet<string>;
  original?: ReadonlySet<string>;
  caption?: string;
}) {
  const total = lines.reduce((sum, l) => sum + (toPaise(l.line_amount) ?? BigInt(0)), BigInt(0));
  return (
    <Table className="min-w-[720px]">
      {caption && <caption className="sr-only">{caption}</caption>}
      <TableHeader>
        <TableRow>
          <TableHead>Line</TableHead>
          <TableHead>Service date</TableHead>
          <TableHead>Service</TableHead>
          <TableHead>Invoice</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="text-right">Unit price</TableHead>
          <TableHead className="text-right">Amount</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => {
          const isFlagged = flagged.has(line.line_id);
          const isOriginal = original.has(line.line_id);
          return (
            <TableRow
              key={line.line_id}
              className={cn(
                isFlagged && "bg-destructive/6 shadow-[inset_3px_0_0_var(--destructive)] hover:bg-destructive/10",
                isOriginal && "bg-primary/6 shadow-[inset_3px_0_0_var(--primary)] hover:bg-primary/10",
              )}
            >
              <TableCell>
                <div className="num font-medium">{line.line_id}</div>
                {isFlagged && <div className="text-[11px] font-medium text-destructive">Flagged line</div>}
                {isOriginal && <div className="text-[11px] font-medium text-primary">Earlier line</div>}
                <SourceRowText source={line.source_row} className="max-w-40" />
              </TableCell>
              <TableCell className="num">{formatDate(line.service_date)}</TableCell>
              <TableCell className="min-w-36 whitespace-normal">
                <div className="text-pretty">{line.service_description}</div>
                <div className="text-xs text-muted-foreground">
                  <span className="font-mono text-[11px]">{line.service_code}</span> · {line.category}
                </div>
              </TableCell>
              <TableCell>
                <div className="num">{line.invoice_reference}</div>
                <div className="max-w-32 truncate text-xs text-muted-foreground" title={line.provider_name}>
                  {line.provider_name}
                </div>
              </TableCell>
              <TableCell className="num text-right">{formatQuantity(line.quantity)}</TableCell>
              <TableCell className="num text-right">{formatINR(line.unit_price)}</TableCell>
              <TableCell className="num text-right font-medium">{formatINR(line.line_amount)}</TableCell>
            </TableRow>
          );
        })}
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={6} className="text-right text-xs font-medium text-muted-foreground">
            {lines.length === 1 ? "1 line" : `${formatNumber(lines.length)} lines`}
          </TableCell>
          <TableCell className="num text-right font-semibold">{formatINR((Number(total) / 100).toFixed(2))}</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
}

function formatQuantity(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? formatNumber(n) : value;
}

/** "₹5,000 per day", "Covered", "Excluded". */
function ruleLimit(rule: PolicyRuleOut): string {
  if (rule.rule_type === "sub_limit" && rule.limit_amount) {
    return `${formatINR(rule.limit_amount)} ${basisLabel(rule.limit_basis).toLowerCase()}`;
  }
  if (rule.rule_type === "exclusion") return "Excluded";
  if (rule.rule_type === "coverage") return "Covered";
  return EMPTY;
}

/** The policy terms and every rule, with the rule in question highlighted. */
export function PolicyPanel({
  policy,
  highlightRuleId,
  id,
  className,
}: {
  policy: PolicyOut;
  highlightRuleId?: string | null;
  id?: string;
  className?: string;
}) {
  const rules = policy.rules ?? [];
  const highlighted = rules.find((r) => r.rule_id === highlightRuleId);
  const others = rules.filter((r) => r !== highlighted);
  return (
    <Panel id={id} aria-labelledby={`${id ?? "policy"}-title`} className={cn("scroll-mt-16", className)}>
      <PanelHeader
        title={
          <span id={`${id ?? "policy"}-title`}>
            Policy <span className="num">{policy.policy_number}</span>
          </span>
        }
        description={`${policy.product_name} · ${policy.policyholder_name}`}
      />
      <div className="space-y-4 px-4 py-3">
        <Facts
          items={[
            {
              label: "Benefit period",
              value: (
                <span className="num">
                  {formatDate(policy.benefit_period_start)} – {formatDate(policy.benefit_period_end)}
                </span>
              ),
              wide: true,
            },
            { label: "Overall limit", value: <span className="num">{formatINR(policy.overall_limit)}</span> },
            {
              label: "Deductible",
              value: (
                <span className="num">
                  {formatINR(policy.deductible_amount)} {basisLabel(policy.deductible_basis).toLowerCase()}
                </span>
              ),
            },
            {
              label: "Co-pay",
              value: <span className="num">{formatPercent(policy.copay_percent, { ratio: false, digits: 0 })}</span>,
            },
            { label: "Insured members", value: policy.insured_member_ids.join(", ") },
            {
              label: "Source row",
              value: <SourceRowText source={policy.source_row} className="text-[13px]" />,
              wide: true,
            },
          ]}
        />
        {highlighted && <RuleCard rule={highlighted} highlighted />}
      </div>
      {others.length > 0 && (
        <details className="group border-t">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium outline-none hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset [&::-webkit-details-marker]:hidden">
            <ChevronRight
              className="size-4 text-muted-foreground transition-transform group-open:rotate-90"
              aria-hidden="true"
            />
            {highlighted ? "Other rules" : "Rules"}
            <span className="num font-normal text-muted-foreground">{formatNumber(others.length)}</span>
          </summary>
          <ul className="space-y-2 px-4 pb-3">
            {others.map((rule) => (
              <li key={rule.rule_id}>
                <RuleCard rule={rule} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

export function RuleCard({ rule, highlighted = false }: { rule: PolicyRuleOut; highlighted?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2 text-[13px]",
        highlighted ? "border-primary/40 bg-primary/5" : "bg-card",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="num font-semibold">{rule.rule_id}</span>
        <Badge variant="outline" className="font-normal text-muted-foreground">
          {ruleTypeLabel(rule.rule_type)}
        </Badge>
        {highlighted && <span className="text-xs font-medium text-primary">Rule applied</span>}
      </div>
      <p className="mt-1 font-medium">{rule.clause_ref}</p>
      {rule.description && <p className="text-muted-foreground">{rule.description}</p>}
      <p className="mt-1 text-xs text-muted-foreground">
        Applies to {basisLabel(rule.scope_type).toLowerCase()}{" "}
        <span className="font-mono text-[11px] text-foreground">{rule.scope_value}</span> ·{" "}
        <span className="num">{ruleLimit(rule)}</span>
      </p>
      <SourceRowText source={rule.source_row} className="mt-1" />
    </div>
  );
}

/** From the requested amount to the payable amount, one step at a time, with a bar per step. */
export function PayableSteps({
  steps,
  requested,
  className,
}: {
  steps: readonly StepOut[];
  requested: string;
  className?: string;
}) {
  if (steps.length === 0) {
    return (
      <p className={cn("px-4 py-3 text-[13px] text-muted-foreground", className)}>
        No payable calculation was recorded.
      </p>
    );
  }
  const max = Math.max(Number(requested) || 0, ...steps.map((s) => Number(s.amount_before) || 0), 1);
  const last = steps[steps.length - 1];
  return (
    <div className={className}>
      <ol className="divide-y">
        <WaterfallRow label="Requested" amount={requested} after={Number(requested)} max={max} strong />
        {steps.map((step) => {
          const reduction = Number(step.reduction) || 0;
          return (
            <li key={step.step_no} className="grid gap-x-4 gap-y-1.5 px-4 py-2.5 sm:grid-cols-[minmax(0,1fr)_14rem]">
              <div className="min-w-0">
                <p className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                  <span className="num text-xs text-muted-foreground">{step.step_no}.</span>
                  <span className="font-medium">{checkName(step.step_code)}</span>
                  {step.policy_rule_id && (
                    <span className="num text-xs text-muted-foreground">{step.policy_rule_id}</span>
                  )}
                </p>
                <p className="mt-0.5 text-[13px] text-pretty text-muted-foreground">{step.explanation}</p>
              </div>
              <div className="space-y-1">
                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className={cn("num", reduction > 0 ? "font-medium text-destructive" : "text-muted-foreground")}>
                    {reduction > 0 ? `−${formatINR(step.reduction)}` : "No change"}
                  </span>
                  <span className="num font-medium">{formatINR(step.amount_after)}</span>
                </div>
                <Bar before={Number(step.amount_before)} after={Number(step.amount_after)} max={max} />
              </div>
            </li>
          );
        })}
        <WaterfallRow label="Payable" amount={last.amount_after} after={Number(last.amount_after)} max={max} strong />
      </ol>
    </div>
  );
}

function WaterfallRow({
  label,
  amount,
  after,
  max,
  strong,
}: {
  label: string;
  amount: string;
  after: number;
  max: number;
  strong?: boolean;
}) {
  return (
    <li className="grid items-center gap-x-4 gap-y-1.5 bg-muted/40 px-4 py-2.5 sm:grid-cols-[minmax(0,1fr)_14rem]">
      <p className={cn("text-[13px]", strong && "font-semibold")}>{label}</p>
      <div className="space-y-1">
        <p className="num text-right text-[13px] font-semibold">{formatINR(amount)}</p>
        <Bar before={after} after={after} max={max} />
      </div>
    </li>
  );
}

/** The amount kept (solid) and the amount removed by this step (hatched). Decorative. */
function Bar({ before, after, max }: { before: number; after: number; max: number }) {
  const kept = Math.max(0, (after / max) * 100);
  const removed = Math.max(0, ((before - after) / max) * 100);
  return (
    <div aria-hidden="true" className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full bg-primary" style={{ width: `${kept}%` }} />
      {removed > 0 && (
        <div
          className="h-full bg-destructive/60"
          style={{
            width: `${removed}%`,
            backgroundImage: "repeating-linear-gradient(135deg, transparent 0 2px, var(--card) 2px 3px)",
          }}
        />
      )}
    </div>
  );
}

/** One validation result: outcome, the rule, expected against actual, and the explanation. */
export function ResultRow({ result, highlighted = false }: { result: ResultOut; highlighted?: boolean }) {
  const impact = Number(result.amount_impact) || 0;
  return (
    <li
      className={cn(
        "grid gap-x-4 gap-y-1 px-4 py-2.5 text-[13px] sm:grid-cols-[6.5rem_minmax(0,1fr)_8rem]",
        highlighted && "bg-destructive/6 shadow-[inset_3px_0_0_var(--destructive)]",
      )}
    >
      <div className="flex items-start gap-2 sm:flex-col sm:gap-1">
        <OutcomeBadge outcome={result.outcome} />
        {result.line_id && <span className="num text-xs text-muted-foreground">{result.line_id}</span>}
      </div>
      <div className="min-w-0 space-y-1">
        <p className="text-pretty">{result.explanation}</p>
        {(result.expected || result.actual) && (
          <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
            {result.expected && (
              <div>
                <dt className="inline text-muted-foreground">Expected </dt>
                <dd className="num inline font-medium">{result.expected}</dd>
              </div>
            )}
            {result.actual && (
              <div>
                <dt className="inline text-muted-foreground">Actual </dt>
                <dd className="num inline font-medium">{result.actual}</dd>
              </div>
            )}
          </dl>
        )}
        {result.policy_rule_id && <p className="num text-xs text-muted-foreground">Rule {result.policy_rule_id}</p>}
      </div>
      <p className={cn("num sm:text-right", impact > 0 ? "font-medium" : "text-muted-foreground")}>
        {impact > 0 ? formatINR(result.amount_impact) : EMPTY}
      </p>
    </li>
  );
}

/** Every validation result grouped by check, failures and adjustments open, passes folded. */
export function ResultsByCheck({ results }: { results: readonly ResultOut[] }) {
  const groups = groupResults(results);
  const totals = outcomeTotals(results);
  if (groups.length === 0) {
    return <p className="px-4 py-3 text-[13px] text-muted-foreground">No checks were recorded for this claim.</p>;
  }
  return (
    <>
      <p className="num border-b px-4 py-2 text-xs text-muted-foreground">
        {formatNumber(results.length)} results · {formatNumber(totals.fail)} failed · {formatNumber(totals.adjusted)}{" "}
        adjusted · {formatNumber(totals.pass)} passed · {formatNumber(totals.not_applicable)} not applicable
      </p>
      <ul className="divide-y">
        {groups.map((group) => (
          <CheckGroupItem key={group.code} group={group} />
        ))}
      </ul>
    </>
  );
}

function CheckGroupItem({ group }: { group: CheckGroup }) {
  const open = group.outcome === "fail" || group.outcome === "adjusted";
  const multiple = group.results.length > 1;
  return (
    <li>
      <details className="group" open={open}>
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 outline-none hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset [&::-webkit-details-marker]:hidden">
          <ChevronRight
            className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
          <span className="num w-8 shrink-0 text-xs text-muted-foreground">{group.code}</span>
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{checkName(group.code, group.name)}</span>
          {multiple && (
            <span className="num hidden text-xs text-muted-foreground sm:inline">
              {formatNumber(group.results.length)} lines
            </span>
          )}
          <OutcomeBadge outcome={group.outcome} />
        </summary>
        <ul className="divide-y border-t bg-muted/20">
          {group.results.map((r) => (
            <ResultRow key={r.id} result={r} />
          ))}
        </ul>
      </details>
    </li>
  );
}

export function SettlementFacts({ settlement }: { settlement: SettlementOut }) {
  return (
    <Facts
      items={[
        { label: "Settlement", value: <span className="num">{settlement.settlement_id}</span> },
        { label: "Settled on", value: <span className="num">{formatDate(settlement.settlement_date)}</span> },
        { label: "Approved", value: <span className="num">{formatINR(settlement.approved_amount)}</span> },
        { label: "Paid", value: <span className="num">{formatINR(settlement.paid_amount)}</span> },
        { label: "Status", value: basisLabel(settlement.settlement_status) },
        { label: "Source row", value: <SourceRowText source={settlement.source_row} className="text-[13px]" /> },
      ]}
    />
  );
}

/** Duplicate checks on a claim: flagged and cleared, each with its reason and signals. */
export function DuplicateDecisions({ matches, claimId }: { matches: readonly MatchOut[]; claimId: string }) {
  if (matches.length === 0) {
    return <p className="px-4 py-3 text-[13px] text-muted-foreground">No duplicate was found for this claim.</p>;
  }
  return (
    <ul className="divide-y">
      {matches.map((m) => {
        const other = m.claim_id === claimId ? m.matched_claim_id : m.claim_id;
        const signals = describeSignals(m.signals);
        return (
          <li key={m.id} className="space-y-1.5 px-4 py-3 text-[13px]">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={m.decision === "cleared" ? "success" : "destructive"}>
                {m.decision === "cleared" ? "Cleared" : "Flagged"}
              </Badge>
              <span className="font-medium">{matchTypeLabel(m.match_type)}</span>
              {m.score && <span className="num text-xs text-muted-foreground">score {formatScore(m.score)}</span>}
              {other !== claimId && (
                <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
                  with <ClaimLink id={other} />
                </span>
              )}
            </div>
            <p className="text-pretty">{m.reason}</p>
            {signals.length > 0 && (
              <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
                {signals.map((s) => (
                  <div key={s.key}>
                    <dt className="inline text-muted-foreground">{s.label}: </dt>
                    <dd className="num inline font-medium">{s.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function ViewClaimLink({ id }: { id: string }) {
  return (
    <Link
      href={`/claims/${encodeURIComponent(id)}`}
      className={cn(linkClass, "inline-flex items-center gap-1 text-[13px]")}
    >
      Open claim
      <ArrowRight className="size-3.5" aria-hidden="true" />
    </Link>
  );
}

export type { ClaimDetail };
