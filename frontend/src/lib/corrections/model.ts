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
