/**
 * Names, order and definitions for alerts: categories, severities, amount types, review
 * statuses, claim types and the checks behind them. No React or network code here, so it
 * is unit tested directly.
 */
import type { Schemas } from "@/lib/api/client";

export type AlertRow = Schemas["AlertRow"];
export type AlertOut = Schemas["AlertOut"];
export type AlertBrief = Schemas["AlertBrief"];
export type AlertDetail = Schemas["AlertDetail"];
export type AlertCategory = Schemas["AlertCategory"];
export type Severity = Schemas["Severity"];
export type AmountType = Schemas["AmountType"];
export type AlertStatus = Schemas["AlertStatus"];
export type ClaimType = Schemas["ClaimType"];
export type ClearedRow = Schemas["ClearedRow"];
export type DashboardSummary = Schemas["Summary"];

/** Categories in the order the plan lists them: policy checks, duplicates, then cross-claim and document findings. */
export const CATEGORIES = [
  "NOT_COVERED",
  "OUT_OF_BENEFIT_PERIOD",
  "EXCLUDED_SERVICE",
  "SUB_LIMIT_EXCEEDED",
  "OVERALL_LIMIT_EXCEEDED",
  "SETTLEMENT_OVERPAYMENT",
  "EXACT_DUPLICATE_CLAIM",
  "DUPLICATE_LINE_ITEM",
  "NEAR_DUPLICATE",
  "EXCESS_FREQUENCY",
  "CROSS_POLICY_INVOICE_REUSE",
  "INCIDENT_CLAIMED_TWICE",
  "CONCURRENT_STAYS",
  "DOCUMENT_REUSED",
  "DOCUMENT_DISCREPANCY",
] as const satisfies readonly AlertCategory[];

export const CATEGORY_LABELS: Record<AlertCategory, string> = {
  NOT_COVERED: "Not covered",
  OUT_OF_BENEFIT_PERIOD: "Out of benefit period",
  EXCLUDED_SERVICE: "Excluded service",
  SUB_LIMIT_EXCEEDED: "Sub-limit exceeded",
  OVERALL_LIMIT_EXCEEDED: "Overall limit exceeded",
  SETTLEMENT_OVERPAYMENT: "Settlement overpayment",
  EXACT_DUPLICATE_CLAIM: "Exact duplicate claim",
  DUPLICATE_LINE_ITEM: "Duplicate line item",
  NEAR_DUPLICATE: "Near-duplicate",
  EXCESS_FREQUENCY: "Excess frequency",
  CROSS_POLICY_INVOICE_REUSE: "Invoice reused across policies",
  INCIDENT_CLAIMED_TWICE: "Incident claimed twice",
  CONCURRENT_STAYS: "Concurrent stays",
  DOCUMENT_REUSED: "Document reused",
  DOCUMENT_DISCREPANCY: "Document discrepancy",
};

/** Duplicate categories show the matched claim side by side. */
export const DUPLICATE_CATEGORIES: readonly AlertCategory[] = [
  "EXACT_DUPLICATE_CLAIM",
  "DUPLICATE_LINE_ITEM",
  "NEAR_DUPLICATE",
  "EXCESS_FREQUENCY",
];

/** Most to least severe. */
export const SEVERITIES = ["critical", "high", "medium", "low", "review"] as const satisfies readonly Severity[];

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  review: "Review",
};

export const AMOUNT_TYPES = ["calculated", "estimated", "suspected"] as const satisfies readonly AmountType[];

export const AMOUNT_TYPE_LABELS: Record<AmountType, string> = {
  calculated: "Calculated",
  estimated: "Estimated",
  suspected: "Suspected",
};

/** The amount type legend, worded as in the plan. */
export const AMOUNT_TYPE_DEFINITIONS: Record<AmountType, string> = {
  calculated: "Determined exactly from policy terms and claim records; the formula is shown.",
  estimated: "A likely amount based on similarity to another record; needs review before any deduction.",
  suspected: "A pattern worth review where no amount can be determined.",
};

export const ALERT_STATUSES = ["open", "reviewed", "dismissed"] as const satisfies readonly AlertStatus[];

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  open: "Open",
  reviewed: "Reviewed",
  dismissed: "Dismissed",
};

export const CLAIM_TYPES = [
  "inpatient",
  "outpatient",
  "daycare",
  "pharmacy",
  "diagnostics",
] as const satisfies readonly ClaimType[];

export const CLAIM_TYPE_LABELS: Record<ClaimType, string> = {
  inpatient: "Inpatient",
  outpatient: "Outpatient",
  daycare: "Day care",
  pharmacy: "Pharmacy",
  diagnostics: "Diagnostics",
};

/** Readable names for the checks (C01-C12) and duplicate patterns. */
const PATTERN_NAMES: Record<string, string> = {
  BENEFIT_PERIOD: "Benefit period",
  INSURED_MEMBER: "Insured member",
  CLAIM_TYPE_COVERED: "Claim type covered",
  LINE_COVERED: "Line covered",
  EXCLUSION: "Exclusion",
  SUB_LIMIT_PER_DAY: "Sub-limit per day",
  SUB_LIMIT_PER_CLAIM: "Sub-limit per claim",
  SUB_LIMIT_PER_PERIOD: "Sub-limit per period",
  SUB_LIMITS: "Sub-limits",
  DEDUCTIBLE: "Deductible",
  COPAY: "Co-pay",
  OVERALL_LIMIT: "Overall limit",
  SETTLEMENT_CHECK: "Settlement check",
  ELIGIBILITY: "Eligibility",
  COVERAGE: "Coverage and exclusions",
  EXACT_CLAIM: "Exact duplicate claim",
  DUPLICATE_LINE: "Duplicate line item",
  NEAR_DUPLICATE: "Near-duplicate",
  LEGITIMATE_REPEAT: "Legitimate repeat",
  EXCESS_FREQUENCY: "Excess frequency",
  CROSS_POLICY_INVOICE_REUSE: "Invoice reused across policies",
  INCIDENT_CLAIMED_TWICE: "Incident claimed twice",
  CONCURRENT_STAYS: "Concurrent stays",
  DOCUMENT_REUSED: "Document reused",
  DOCUMENT_DISCREPANCY: "Document discrepancy",
};

function humanize(value: string): string {
  const words = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Splits a rule or pattern into its check code and a readable name:
 * "C06 SUB_LIMIT_PER_DAY" -> { code: "C06", name: "Sub-limit per day" },
 * "NEAR_DUPLICATE" -> { code: null, name: "Near-duplicate" }.
 */
export function describePattern(value: string | null | undefined): { code: string | null; name: string } {
  if (!value) return { code: null, name: "" };
  const match = /^(C\d{2})\s+(.+)$/.exec(value.trim());
  const code = match ? match[1] : null;
  const key = (match ? match[2] : value).trim();
  return { code, name: PATTERN_NAMES[key] ?? humanize(key) };
}

/** A check result's readable name from its code and the backend's name ("C06", "SUB_LIMIT_PER_DAY"). */
export function checkName(code: string, name?: string | null): string {
  return describePattern(name ? `${code} ${name}` : code).name || code;
}

function labelOf<K extends string>(labels: Record<K, string>, value: string): string {
  return (labels as Record<string, string>)[value] ?? humanize(value);
}

export const categoryLabel = (value: string) => labelOf(CATEGORY_LABELS, value);
export const severityLabel = (value: string) => labelOf(SEVERITY_LABELS, value);
export const amountTypeLabel = (value: string) => labelOf(AMOUNT_TYPE_LABELS, value);
export const alertStatusLabel = (value: string) => labelOf(ALERT_STATUS_LABELS, value);
export const claimTypeLabel = (value: string) => labelOf(CLAIM_TYPE_LABELS, value);

/** Rank for sorting: 0 is most severe; unknown values sort last. */
export function severityRank(value: string): number {
  const index = (SEVERITIES as readonly string[]).indexOf(value);
  return index < 0 ? SEVERITIES.length : index;
}

/** Sorts category rows into the plan's order, unknown categories last. */
export function categoryRank(value: string): number {
  const index = (CATEGORIES as readonly string[]).indexOf(value);
  return index < 0 ? CATEGORIES.length : index;
}
