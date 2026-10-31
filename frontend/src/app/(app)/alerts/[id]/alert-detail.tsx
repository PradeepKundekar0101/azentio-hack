"use client";

import { ArrowLeft, SearchX } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { LoadError } from "@/components/app-shell/states";
import { EmptyState } from "@/components/empty-state";
import { PageHeader, Panel, PanelHeader } from "@/components/page";
import { AlertAmount, AlertStatusBadge, OutcomeBadge, SeverityBadge } from "@/components/review/badges";
import {
  ClaimLink,
  claimFacts,
  Facts,
  LinesTable,
  PayableSteps,
  PolicyPanel,
  RuleCard,
  SettlementFacts,
  SourceRowText,
  ViewClaimLink,
} from "@/components/review/claim-parts";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useAlert } from "@/lib/alerts/hooks";
import {
  AMOUNT_TYPE_DEFINITIONS,
  type AlertDetail,
  type AlertOut,
  type AmountType,
  categoryLabel,
  claimTypeLabel,
  describePattern,
  DUPLICATE_CATEGORIES,
} from "@/lib/alerts/model";
import {
  affectedLineIds,
  claimLineSummary,
  type ClaimDetail,
  type ComparedClaimField,
  describeSignals,
  differingFields,
  formatScore,
  matchTypeLabel,
  type MatchOut,
  type ResultOut,
  type SourceRow,
} from "@/lib/claims/model";
import { EMPTY, formatDate, formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ReviewActions } from "./review-actions";

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

export function AlertDetailView({ id: rawId }: { id: string }) {
  const id = /^\d+$/.test(rawId) ? Number(rawId) : NaN;
  if (!Number.isSafeInteger(id) || id < 1) return <AlertNotFound />;
  return <AlertView id={id} />;
}

function AlertNotFound() {
  return (
    <>
      <BackLink />
      <EmptyState
        icon={SearchX}
        title="Alert not found"
        description="This alert does not exist. Alerts are replaced when claims are validated again, so the link may be out of date."
        actions={
          <Button asChild variant="outline">
            <Link href="/alerts">Back to Alerts</Link>
          </Button>
        }
      />
    </>
  );
}

/** The validation result behind an alert, named in its supporting record. */
function findResult(detail: AlertDetail): ResultOut | undefined {
  const ref = detail.alert.supporting?.validation_result as
    { check_code?: string; line_id?: string | null } | undefined;
  if (!ref?.check_code) return undefined;
  return detail.claim.results.find(
    (r) => r.check_code === ref.check_code && (r.line_id ?? null) === (ref.line_id ?? null),
  );
}

function AlertView({ id }: { id: number }) {
  const query = useAlert(id);
  const loaded = query.isSuccess;

  // A link to a section (e.g. #policy) arrives before the data; scroll once it has rendered.
  useEffect(() => {
    if (!loaded || !window.location.hash) return;
    document.getElementById(decodeURIComponent(window.location.hash.slice(1)))?.scrollIntoView({ block: "start" });
  }, [loaded]);

  if (query.isPending) return <AlertDetailSkeleton />;
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <AlertNotFound />;
    return <LoadError message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  }

  const detail = query.data;
  const { alert, claim, matched_claim: matched, match } = detail;
  const result = findResult(detail);
  const ruleId =
    alert.policy_rule_id ??
    (alert.supporting?.policy_rule_id as string | null | undefined) ??
    result?.policy_rule_id ??
    null;
  const rule = claim.policy.rules?.find((r) => r.rule_id === ruleId);
  const flagged = affectedLineIds(alert);
  const isDuplicate = DUPLICATE_CATEGORIES.includes(alert.category as never);
  const isSettlement = alert.category === "SETTLEMENT_OVERPAYMENT";
  // A duplicate line within the same claim: the earlier line is in this claim too.
  const earlierHere = new Set(match && !matched && match.matched_line_id ? [match.matched_line_id] : []);

  const sections = [
    { href: "#rule", label: "Rule or pattern" },
    { href: "#claim", label: "Claim lines" },
    ...(matched ? [{ href: "#matched", label: "Matched claim" }] : []),
    ...(isSettlement ? [{ href: "#settlement", label: "Settlement" }] : []),
    { href: "#policy", label: rule ? "Policy rule" : "Policy" },
    { href: "#sources", label: "Source rows" },
  ];

  return (
    <>
      <BackLink />
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span>
              <span className="num">Alert #{alert.id}</span>
              <span className="text-muted-foreground"> · </span>
              {categoryLabel(alert.category)}
            </span>
            <SeverityBadge severity={alert.severity} />
            <AlertStatusBadge status={alert.status} />
          </span>
        }
        description={
          <>
            Claim <ClaimLink id={alert.claim_id} /> · {claim.claim.claimant_name} · raised{" "}
            <span className="num">{formatDateTime(alert.created_at)}</span>
          </>
        }
        actions={<ReviewActions alert={alert} />}
      />

      <nav aria-label="On this page" className="mb-4 flex flex-wrap gap-1.5">
        {sections.map((s) => (
          <a
            key={s.href}
            href={s.href}
            className="rounded-full border bg-card px-2.5 py-0.5 text-xs font-medium text-muted-foreground outline-none hover:border-primary/40 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            {s.label}
          </a>
        ))}
      </nav>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="min-w-0 space-y-4 xl:col-span-2">
          <Summary alert={alert} />
          <RulePanel alert={alert} result={result} match={match} rule={rule ?? null} isDuplicate={isDuplicate} />

          <Panel id="claim" aria-labelledby="claim-title" className="scroll-mt-16">
            <PanelHeader
              title={
                <span id="claim-title">
                  Claim <span className="num">{claim.claim.claim_id}</span>
                </span>
              }
              description={
                flagged.size > 0
                  ? "All lines of the claim. The lines this alert is about are highlighted."
                  : "All lines of the claim. The alert applies to the claim as a whole."
              }
              actions={<ViewClaimLink id={claim.claim.claim_id} />}
            />
            <div className="px-4 py-3">
              <Facts items={claimFacts(claim.claim)} />
            </div>
            <div className="border-t">
              <LinesTable lines={claim.lines} flagged={flagged} original={earlierHere} caption="Claim lines" />
            </div>
          </Panel>

          {matched && match && <DuplicateComparison claim={claim} matched={matched} match={match} />}

          {isSettlement && <SettlementPanel claim={claim} result={result} />}
        </div>

        <div className="min-w-0 space-y-4">
          <PolicyPanel id="policy" policy={claim.policy} highlightRuleId={rule?.rule_id} />
          <SourcesPanel detail={detail} rule={rule ?? null} flagged={flagged} />
        </div>
      </div>
    </>
  );
}

function Summary({ alert }: { alert: AlertOut }) {
  return (
    <Panel aria-label="Summary" className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <p className="text-xs text-muted-foreground">{alert.amount_type === "suspected" ? "Amount" : "Leakage"}</p>
          <AlertAmount amount={alert.amount} type={alert.amount_type} size="lg" className="mt-0.5" />
        </div>
        <p className="max-w-sm text-xs text-pretty text-muted-foreground">
          {AMOUNT_TYPE_DEFINITIONS[alert.amount_type as AmountType]}
        </p>
      </div>
      <p className="text-sm leading-6 text-pretty">{alert.explanation}</p>
      {(alert.review_note || alert.reviewed_at) && (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-[13px]">
          <p className="text-xs font-medium text-muted-foreground">
            {alert.status === "dismissed" ? "Dismissed" : alert.status === "reviewed" ? "Reviewed" : "Last review"}
            {alert.reviewed_at && <span className="num"> {formatDateTime(alert.reviewed_at)}</span>}
          </p>
          {alert.review_note && <p className="mt-0.5 whitespace-pre-line">{alert.review_note}</p>}
        </div>
      )}
    </Panel>
  );
}

function RulePanel({
  alert,
  result,
  match,
  rule,
  isDuplicate,
}: {
  alert: AlertOut;
  result: ResultOut | undefined;
  match: MatchOut | null;
  rule: NonNullable<ClaimDetail["policy"]["rules"]>[number] | null;
  isDuplicate: boolean;
}) {
  const pattern = describePattern(alert.rule_or_pattern);
  const inputs = result?.inputs ? Object.entries(result.inputs).filter(([k]) => k !== "formula") : [];
  return (
    <Panel id="rule" aria-labelledby="rule-title" className="scroll-mt-16">
      <PanelHeader title={<span id="rule-title">Rule or pattern</span>} />
      <div className="space-y-4 px-4 py-3">
        <Facts
          items={[
            {
              label: isDuplicate ? "Duplicate pattern" : "Check",
              value: (
                <span>
                  {pattern.code && <span className="num mr-1.5 text-muted-foreground">{pattern.code}</span>}
                  {pattern.name || (match ? matchTypeLabel(match.match_type) : EMPTY)}
                </span>
              ),
            },
            {
              label: "Policy rule",
              value: rule ? (
                <a
                  href="#policy"
                  className="rounded-sm text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="num">{rule.rule_id}</span>
                  <span className="text-muted-foreground"> · {rule.clause_ref}</span>
                </a>
              ) : (
                <span className="font-normal text-muted-foreground">
                  {isDuplicate ? "Not a policy rule: found by comparing claims" : "Policy terms (no single rule)"}
                </span>
              ),
            },
            ...(match?.score
              ? [{ label: "Similarity score", value: <span className="num">{formatScore(match.score)}</span> }]
              : []),
            ...(result ? [{ label: "Outcome", value: <OutcomeBadge outcome={result.outcome} /> }] : []),
          ]}
        />
        {alert.calculation && (
          <div>
            <p className="text-xs text-muted-foreground">Calculation</p>
            <p className="num mt-1 rounded-md border bg-muted/40 px-3 py-2 text-sm font-medium [overflow-wrap:anywhere]">
              {alert.calculation}
            </p>
          </div>
        )}
        {result && (result.expected || result.actual) && (
          <div className="grid gap-3 sm:grid-cols-3">
            <ValueBox label="Expected" value={result.expected} />
            <ValueBox label="Actual" value={result.actual} tone="destructive" />
            <ValueBox
              label="Difference"
              value={Number(result.amount_impact) > 0 ? formatINR(result.amount_impact) : null}
            />
          </div>
        )}
        {inputs.length > 0 && (
          <details className="group text-[13px]">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
              Inputs used
            </summary>
            <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
              {inputs.map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="font-mono text-xs text-muted-foreground">{key}</dt>
                  <dd className="num [overflow-wrap:anywhere]">{formatInput(value)}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}
        {match && match.reason !== alert.explanation && (
          <p className="text-[13px] text-pretty text-muted-foreground">{match.reason}</p>
        )}
      </div>
    </Panel>
  );
}

function formatInput(value: unknown): string {
  if (value === null || value === undefined || value === "") return EMPTY;
  if (Array.isArray(value)) return value.length ? value.map(String).join(", ") : EMPTY;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ValueBox({ label, value, tone }: { label: string; value: string | null; tone?: "destructive" }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("num mt-0.5 text-sm font-semibold", tone === "destructive" && value && "text-destructive")}>
        {value ?? EMPTY}
      </p>
    </div>
  );
}

const COMPARE_ROWS: { field: ComparedClaimField; label: string; value: (d: ClaimDetail) => React.ReactNode }[] = [
  { field: "claimant_name", label: "Claimant", value: (d) => d.claim.claimant_name },
  { field: "claimant_id", label: "Member ID", value: (d) => d.claim.claimant_id },
  { field: "policy_number", label: "Policy", value: (d) => d.claim.policy_number },
  { field: "providers", label: "Provider", value: (d) => claimLineSummary(d.lines).providers.join(", ") || EMPTY },
  { field: "invoices", label: "Invoice", value: (d) => claimLineSummary(d.lines).invoices.join(", ") || EMPTY },
  { field: "incident_reference", label: "Incident reference", value: (d) => d.claim.incident_reference ?? EMPTY },
  { field: "claim_type", label: "Claim type", value: (d) => claimTypeLabel(d.claim.claim_type) },
  { field: "incident_date", label: "Incident date", value: (d) => formatDate(d.claim.incident_date) },
  { field: "submission_date", label: "Submitted", value: (d) => formatDate(d.claim.submission_date) },
  { field: "services", label: "Service codes", value: (d) => claimLineSummary(d.lines).services.join(", ") || EMPTY },
  { field: "requested_amount", label: "Requested", value: (d) => formatINR(d.claim.requested_amount) },
  { field: "status", label: "Status", value: (d) => (d.claim.status === "settled" ? "Settled" : "Open") },
];

function DuplicateComparison({ claim, matched, match }: { claim: ClaimDetail; matched: ClaimDetail; match: MatchOut }) {
  const diff = differingFields(claim, matched);
  const signals = describeSignals(match.signals);
  const matchedLines = new Set(match.matched_line_id ? [match.matched_line_id] : []);
  return (
    <Panel id="matched" aria-labelledby="matched-title" className="scroll-mt-16">
      <PanelHeader
        title={<span id="matched-title">Compared with the earlier claim</span>}
        description={
          diff.size === 0
            ? "Every compared field is the same."
            : "Fields that differ are highlighted. Everything else is the same."
        }
        actions={<ViewClaimLink id={matched.claim.claim_id} />}
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-[13px]">
          <caption className="sr-only">This claim and the earlier claim side by side</caption>
          <thead>
            <tr className="border-b bg-(--table-head) text-xs text-muted-foreground">
              <th scope="col" className="h-9 w-44 px-4 text-left font-semibold">
                Field
              </th>
              <th scope="col" className="h-9 px-3 text-left font-semibold">
                This claim <ClaimLink id={claim.claim.claim_id} className="ml-1" />
              </th>
              <th scope="col" className="h-9 px-3 pr-4 text-left font-semibold">
                Earlier claim <ClaimLink id={matched.claim.claim_id} className="ml-1" />
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {COMPARE_ROWS.map((row) => {
              const differs = diff.has(row.field);
              return (
                <tr key={row.field} className={cn(differs && "bg-warning/8")}>
                  <th scope="row" className="px-4 py-2 text-left align-top font-normal text-muted-foreground">
                    {row.label}
                    {differs && <span className="ml-1.5 text-[11px] font-medium text-warning">Differs</span>}
                  </th>
                  <td className={cn("num px-3 py-2 align-top [overflow-wrap:anywhere]", differs && "font-medium")}>
                    {row.value(claim)}
                  </td>
                  <td className={cn("num px-3 py-2 pr-4 align-top [overflow-wrap:anywhere]", differs && "font-medium")}>
                    {row.value(matched)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {signals.length > 0 && (
        <div className="border-t px-4 py-3">
          <h3 className="text-xs font-semibold text-muted-foreground">
            Similarity signals
            {match.score && (
              <span className="num ml-2 font-medium text-foreground">Score {formatScore(match.score)}</span>
            )}
          </h3>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {signals.map((s) => (
              <div key={s.key} className="rounded-md border px-3 py-2">
                <dt className="text-xs text-muted-foreground">{s.label}</dt>
                <dd className="num mt-0.5 text-sm font-semibold [overflow-wrap:anywhere]">{s.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <div className="border-t">
        <p className="px-4 pt-3 text-xs font-semibold text-muted-foreground">Earlier claim lines</p>
        <LinesTable lines={matched.lines} original={matchedLines} caption="Earlier claim lines" />
      </div>
      {matched.settlement && (
        <div className="border-t px-4 py-3">
          <p className="mb-2 text-xs font-semibold text-muted-foreground">Settlement of the earlier claim</p>
          <SettlementFacts settlement={matched.settlement} />
        </div>
      )}
    </Panel>
  );
}

function SettlementPanel({ claim, result }: { claim: ClaimDetail; result: ResultOut | undefined }) {
  const entitlement = result?.inputs?.entitlement as string | undefined;
  const reasons = (result?.inputs?.reasons as string[] | undefined) ?? [];
  return (
    <Panel id="settlement" aria-labelledby="settlement-title" className="scroll-mt-16">
      <PanelHeader
        title={<span id="settlement-title">Settlement and recomputed entitlement</span>}
        description="What was paid, against what the policy terms allow when every step is applied."
      />
      {claim.settlement ? (
        <div className="space-y-3 px-4 py-3">
          <SettlementFacts settlement={claim.settlement} />
          {entitlement && (
            <div className="grid gap-3 sm:grid-cols-3">
              <ValueBox label="Paid" value={formatINR(claim.settlement.paid_amount)} tone="destructive" />
              <ValueBox label="Entitlement" value={formatINR(entitlement)} />
              <ValueBox label="Overpaid" value={result ? formatINR(result.amount_impact) : null} />
            </div>
          )}
          {reasons.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-[13px]">
              {reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="px-4 py-3 text-[13px] text-muted-foreground">No settlement record was found.</p>
      )}
      <div className="border-t">
        <p className="px-4 pt-3 text-xs font-semibold text-muted-foreground">Recomputed payable, step by step</p>
        <PayableSteps steps={claim.payable_steps} requested={claim.claim.requested_amount} className="mt-2" />
      </div>
    </Panel>
  );
}

function SourcesPanel({
  detail,
  rule,
  flagged,
}: {
  detail: AlertDetail;
  rule: NonNullable<ClaimDetail["policy"]["rules"]>[number] | null;
  flagged: Set<string>;
}) {
  const { claim, matched_claim: matched, match } = detail;
  const rows: { label: string; id: string; source: SourceRow | null | undefined }[] = [
    { label: "Claim", id: claim.claim.claim_id, source: claim.claim.source_row },
    ...claim.lines
      .filter((l) => flagged.has(l.line_id) || l.line_id === match?.matched_line_id)
      .map((l) => ({ label: "Line", id: l.line_id, source: l.source_row })),
    { label: "Policy", id: claim.policy.policy_number, source: claim.policy.source_row },
    ...(rule ? [{ label: "Policy rule", id: rule.rule_id, source: rule.source_row }] : []),
    ...(claim.settlement
      ? [{ label: "Settlement", id: claim.settlement.settlement_id, source: claim.settlement.source_row }]
      : []),
    ...(matched
      ? [
          { label: "Earlier claim", id: matched.claim.claim_id, source: matched.claim.source_row },
          ...matched.lines
            .filter((l) => l.line_id === match?.matched_line_id)
            .map((l) => ({ label: "Earlier line", id: l.line_id, source: l.source_row })),
          ...(matched.settlement
            ? [
                {
                  label: "Earlier settlement",
                  id: matched.settlement.settlement_id,
                  source: matched.settlement.source_row,
                },
              ]
            : []),
        ]
      : []),
  ];
  return (
    <Panel id="sources" aria-labelledby="sources-title" className="scroll-mt-16">
      <PanelHeader
        title={<span id="sources-title">Source rows</span>}
        description="The file, sheet and row each supporting record was read from."
      />
      <ul className="divide-y">
        {rows.map((row) => (
          <li key={`${row.label}-${row.id}`} className="flex flex-col gap-0.5 px-4 py-2 text-[13px]">
            <span>
              <span className="text-muted-foreground">{row.label} </span>
              <span className="num font-medium">{row.id}</span>
            </span>
            <SourceRowText source={row.source} />
          </li>
        ))}
      </ul>
      {rule && (
        <div className="border-t px-4 py-3 xl:hidden">
          <RuleCard rule={rule} highlighted />
        </div>
      )}
    </Panel>
  );
}

export function AlertDetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading alert">
      <Skeleton className="mb-3 h-4 w-16" />
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-7 w-72 max-w-full" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <Skeleton className="h-8 w-48" />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Skeleton className="h-36 rounded-lg" />
          <Skeleton className="h-56 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-72 rounded-lg" />
          <Skeleton className="h-48 rounded-lg" />
        </div>
      </div>
    </div>
  );
}
