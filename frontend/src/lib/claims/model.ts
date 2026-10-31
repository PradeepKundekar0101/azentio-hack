/**
 * Pure helpers for claim and alert detail pages: grouping validation results by check,
 * comparing a claim with its matched duplicate, source-row labels and duplicate signals.
 */
import type { Schemas } from "@/lib/api/client";

import { formatDate, formatINR, formatNumber, toPaise } from "../format";

export type ClaimDetail = Schemas["ClaimDetail"];
export type ClaimOut = Schemas["ClaimOut"];
export type LineOut = Schemas["LineOut"];
export type PolicyOut = Schemas["PolicyOut"];
export type PolicyRuleOut = Schemas["PolicyRuleOut"];
export type ResultOut = Schemas["ResultOut"];
export type StepOut = Schemas["StepOut"];
export type MatchOut = Schemas["MatchOut"];
export type SettlementOut = Schemas["SettlementOut"];
export type SourceRow = Schemas["SourceRow"];

export type Outcome = "fail" | "adjusted" | "pass" | "not_applicable";

export const OUTCOME_LABELS: Record<Outcome, string> = {
  fail: "Fail",
  adjusted: "Adjusted",
  pass: "Pass",
  not_applicable: "Not applicable",
};

export function outcomeLabel(value: string): string {
  return OUTCOME_LABELS[value as Outcome] ?? value;
}

/** Fail outranks adjusted, which outranks pass, then not applicable. */
const OUTCOME_RANK: Record<string, number> = { fail: 0, adjusted: 1, pass: 2, not_applicable: 3 };

export interface CheckGroup {
  code: string;
  name: string | null;
  /** The most significant outcome in the group. */
  outcome: string;
  results: ResultOut[];
  counts: Record<Outcome, number>;
}

/** Results grouped by check code (C01, C02, ...) in code order; each group keeps line order. */
export function groupResults(results: readonly ResultOut[]): CheckGroup[] {
  const groups = new Map<string, CheckGroup>();
  for (const result of results) {
    let group = groups.get(result.check_code);
    if (!group) {
      group = {
        code: result.check_code,
        name: result.check_name ?? null,
        outcome: result.outcome,
        results: [],
        counts: { fail: 0, adjusted: 0, pass: 0, not_applicable: 0 },
      };
      groups.set(result.check_code, group);
    }
    group.results.push(result);
    if (result.outcome in group.counts) group.counts[result.outcome as Outcome] += 1;
    if ((OUTCOME_RANK[result.outcome] ?? 9) < (OUTCOME_RANK[group.outcome] ?? 9)) group.outcome = result.outcome;
  }
  return [...groups.values()].sort((a, b) => a.code.localeCompare(b.code, "en", { numeric: true }));
}

/** Totals across all results, for the summary line above the list. */
export function outcomeTotals(results: readonly ResultOut[]): Record<Outcome, number> {
  const totals: Record<Outcome, number> = { fail: 0, adjusted: 0, pass: 0, not_applicable: 0 };
  for (const r of results) if (r.outcome in totals) totals[r.outcome as Outcome] += 1;
  return totals;
}

/** "claims.xlsx · Claims · Row 14", "line_items.csv · Row 3", or null when unknown. */
export function sourceRowLabel(source: SourceRow | null | undefined): string | null {
  if (!source || (!source.file_name && source.row_number == null)) return null;
  const parts: string[] = [];
  if (source.file_name) parts.push(source.file_name);
  if (source.sheet) parts.push(source.sheet);
  if (source.row_number != null) parts.push(`Row ${formatNumber(source.row_number)}`);
  return parts.join(" · ");
}

/** The fields compared side by side for a duplicate pair, in display order. */
export const COMPARED_CLAIM_FIELDS = [
  "claimant_name",
  "claimant_id",
  "policy_number",
  "claim_type",
  "incident_date",
  "submission_date",
  "incident_reference",
  "requested_amount",
  "status",
] as const satisfies readonly (keyof ClaimOut)[];
export type ComparedClaimField = (typeof COMPARED_CLAIM_FIELDS)[number] | "invoices" | "providers" | "services";

function sameMoney(a: string | null | undefined, b: string | null | undefined): boolean {
  const pa = toPaise(a);
  const pb = toPaise(b);
  return pa === pb;
}

function setOf(values: Iterable<string>): string {
  return [...new Set(values)].sort().join("|");
}

/** Invoice references, providers and service codes of a claim, for the comparison. */
export function claimLineSummary(lines: readonly LineOut[]) {
  return {
    invoices: [...new Set(lines.map((l) => l.invoice_reference))],
    providers: [...new Set(lines.map((l) => l.provider_name))],
    services: [...new Set(lines.map((l) => l.service_code))],
  };
}

/** Fields that differ between a claim and its matched claim (amounts compared exactly). */
export function differingFields(a: ClaimDetail, b: ClaimDetail): Set<ComparedClaimField> {
  const out = new Set<ComparedClaimField>();
  for (const field of COMPARED_CLAIM_FIELDS) {
    const va = a.claim[field];
    const vb = b.claim[field];
    const same = field === "requested_amount" ? sameMoney(va as string, vb as string) : (va ?? "") === (vb ?? "");
    if (!same) out.add(field);
  }
  const la = claimLineSummary(a.lines);
  const lb = claimLineSummary(b.lines);
  for (const key of ["invoices", "providers", "services"] as const) {
    if (setOf(la[key]) !== setOf(lb[key])) out.add(key);
  }
  return out;
}

/** Lines an alert points at: its own line and the supporting line IDs. */
export function affectedLineIds(alert: { line_id: string | null; supporting: Record<string, unknown> }): Set<string> {
  const ids = new Set<string>();
  if (alert.line_id) ids.add(alert.line_id);
  const supported = alert.supporting?.line_ids;
  if (Array.isArray(supported)) for (const id of supported) if (typeof id === "string") ids.add(id);
  return ids;
}

const SIGNAL_LABELS: Record<string, string> = {
  reference_similarity: "Invoice reference similarity",
  date_gap_days: "Days apart",
  amount_difference: "Amount difference",
  code_overlap: "Service code overlap",
  same_provider: "Same provider",
  overlapping_amount: "Overlapping amount",
  references: "Invoice references",
  excess_frequency: "Above weekly maximum",
  requested_amount: "Requested amount",
  line_amount: "Line amount",
  basis: "Matched on",
  scope: "Scope",
  count_in_week: "Count in the week",
  max_per_week: "Weekly maximum",
  min_interval_days: "Minimum interval",
};

/** Signals shown first, in this order; the rest follow alphabetically. */
const SIGNAL_ORDER = [
  "reference_similarity",
  "date_gap_days",
  "amount_difference",
  "code_overlap",
  "same_provider",
  "references",
  "overlapping_amount",
];

const MONEY_SIGNALS = new Set(["overlapping_amount", "requested_amount", "line_amount"]);

function signalValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "–";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (MONEY_SIGNALS.has(key)) return formatINR(value as string);
  if (key === "amount_difference") {
    const n = Number(value);
    return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : String(value);
  }
  if (key === "date_gap_days" || key === "min_interval_days") {
    const n = Number(value);
    return Number.isFinite(n) ? `${formatNumber(n)} ${n === 1 ? "day" : "days"}` : String(value);
  }
  if (key === "references" && Array.isArray(value)) {
    return value.map((side) => (Array.isArray(side) ? side.join(", ") : String(side))).join(" vs ");
  }
  if (key === "basis")
    return value === "invoices" ? "Invoice references" : value === "incident" ? "Incident reference" : String(value);
  if (key === "scope")
    return value === "within_claim" ? "Within the claim" : value === "across_claims" ? "Across claims" : String(value);
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value);
  return String(value);
}

export interface Signal {
  key: string;
  label: string;
  value: string;
}

/** Duplicate-match signals as labelled, formatted rows. */
export function describeSignals(signals: Record<string, unknown> | null | undefined): Signal[] {
  if (!signals) return [];
  const keys = Object.keys(signals).sort((a, b) => {
    const ia = SIGNAL_ORDER.indexOf(a);
    const ib = SIGNAL_ORDER.indexOf(b);
    if (ia >= 0 || ib >= 0) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    return a.localeCompare(b);
  });
  return keys.map((key) => ({
    key,
    label: SIGNAL_LABELS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
    value: signalValue(key, signals[key]),
  }));
}

/** A score such as "0.8900" as "0.89". */
export function formatScore(score: string | number | null | undefined): string {
  if (score === null || score === undefined || score === "") return "–";
  const n = Number(score);
  return Number.isFinite(n) ? n.toFixed(2) : String(score);
}

const MATCH_TYPE_LABELS: Record<string, string> = {
  exact_claim: "Exact duplicate claim",
  duplicate_line: "Duplicate line item",
  near_duplicate: "Near-duplicate",
  legitimate_repeat: "Legitimate repeat",
  excess_frequency: "Excess frequency",
};

export function matchTypeLabel(value: string): string {
  return MATCH_TYPE_LABELS[value] ?? value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** "Per claim" etc. for deductible and limit bases. */
export function basisLabel(value: string | null | undefined): string {
  if (!value) return "–";
  return value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** "Sub-limit", "Coverage", "Exclusion". */
export function ruleTypeLabel(value: string): string {
  if (value === "sub_limit") return "Sub-limit";
  return basisLabel(value);
}
