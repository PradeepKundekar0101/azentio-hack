/** Pure helpers for the corrections table: applied steps, items for review, the recovery, and reconciliation. */
import type { Schemas } from "@/lib/api/client";

import { toPaise } from "../format";

export type CorrectionSetOut = Schemas["CorrectionSetOut"];
export type CorrectionOut = Schemas["CorrectionOut"];
export type CorrectionSetSummary = Schemas["CorrectionSetSummary"];

export function splitCorrections(set: CorrectionSetOut) {
  const recovery = set.corrections.find((c) => c.type === "RECOVER_OVERPAYMENT") ?? null;
  return {
    applied: set.corrections.filter((c) => c.applied && c.type !== "RECOVER_OVERPAYMENT"),
    review: set.corrections.filter((c) => !c.applied),
    recovery,
  };
}

/** Requested minus the applied steps equals the recommended payable, to the paisa. */
export function reconciles(set: CorrectionSetOut): boolean {
  const { applied } = splitCorrections(set);
  const total = applied.reduce((sum, c) => sum + (toPaise(c.difference) ?? BigInt(0)), BigInt(0));
  return (toPaise(set.requested_amount) ?? BigInt(0)) - total === toPaise(set.recommended_payable);
}

const LABELS: Record<string, string> = {
  SET_PAYABLE_TO_ZERO: "Set payable to zero",
  ALIGN_TO_LINE_TOTAL: "Align to line items",
  REMOVE_DUPLICATE_LINE: "Remove repeated line",
  REMOVE_UNSUPPORTED_LINE: "Remove unsupported line",
  ADJUST_TO_DOCUMENT: "Adjust to invoice",
  REDUCE_ROOM_DAYS: "Reduce room days",
  REMOVE_EXCLUDED_LINE: "Remove excluded line",
  REMOVE_UNCOVERED_LINE: "Remove uncovered line",
  CAP_AT_SUB_LIMIT: "Cap at sub-limit",
  APPLY_DEDUCTIBLE: "Apply deductible",
  APPLY_COPAY: "Apply co-pay",
  CAP_AT_OVERALL_LIMIT: "Cap at overall limit",
  RECOVER_OVERPAYMENT: "Recover overpayment",
};

export function correctionLabel(type: string): string {
  return LABELS[type] ?? type.toLowerCase().replaceAll("_", " ");
}

export function evidenceKind(ref: string): string {
  if (ref.startsWith("DSC-")) return "Document discrepancy";
  if (ref.startsWith("REL-")) return "Related claims";
  if (ref.startsWith("ALR-")) return "Alert";
  if (ref.startsWith("STL-")) return "Settlement";
  return "Evidence";
}

const DOCUMENT_TYPES = new Set(["REMOVE_DUPLICATE_LINE", "REMOVE_UNSUPPORTED_LINE", "ADJUST_TO_DOCUMENT", "REDUCE_ROOM_DAYS", "ALIGN_TO_LINE_TOTAL"]);
const TERM_TYPES = new Set(["APPLY_DEDUCTIBLE", "APPLY_COPAY"]);

function rupees(paise: bigint): string {
  return `${paise / BigInt(100)}.${(paise % BigInt(100)).toString().padStart(2, "0")}`;
}

/** Where the reduction comes from: what the documents and duplicates do not support, what is above the policy's
 * limits (or not covered), and the normal deductible and co-pay. */
export function settlementSummary(set: CorrectionSetOut): { documents: string; policyLimits: string; policyTerms: string } {
  const totals = { documents: BigInt(0), policyLimits: BigInt(0), policyTerms: BigInt(0) };
  for (const c of splitCorrections(set).applied) {
    const paise = toPaise(c.difference) ?? BigInt(0);
    if (DOCUMENT_TYPES.has(c.type)) totals.documents += paise;
    else if (TERM_TYPES.has(c.type)) totals.policyTerms += paise;
    else totals.policyLimits += paise;
  }
  return { documents: rupees(totals.documents), policyLimits: rupees(totals.policyLimits), policyTerms: rupees(totals.policyTerms) };
}
