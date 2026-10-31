/** How a claim stands after validation, for the claims list. */

export type ClaimReview = "clean" | "flagged" | "not_validated";

export const REVIEW_LABELS: Record<ClaimReview, string> = {
  clean: "Clean, ready to pay",
  flagged: "Flagged",
  not_validated: "Not validated",
};

export const REVIEW_HINTS: Record<ClaimReview, string> = {
  clean: "Validated with no alerts: the payable amount can be settled as shown.",
  flagged: "Has alerts to review before settlement.",
  not_validated: "Not processed yet: run validation from its import.",
};

export const NOTHING_PAYABLE_HINT =
  "Covered and valid, but the deductible, co-pay or limits leave nothing to pay.";

/** A clean claim whose payable is ₹0 is not "ready to pay": say so. */
export function isNothingPayable(review: string, payable: string | null | undefined): boolean {
  return review === "clean" && payable !== null && payable !== undefined && Number(payable) === 0;
}

export function reviewLabel(review: string, payable?: string | null): string {
  if (isNothingPayable(review, payable)) return "Clean, nothing payable";
  return REVIEW_LABELS[review as ClaimReview] ?? review;
}

/** Statuses the list understands; anything else in the URL falls back to the default. */
export function parseStatus(value: string): "open" | "settled" | "all" {
  return value === "settled" || value === "all" ? value : "open";
}

export function parseReview(value: string): "clean" | "flagged" | "not_validated" | "all" {
  return value === "clean" || value === "flagged" || value === "not_validated" ? value : "all";
}

export const CLAIM_SORTS = [
  { value: "-incident_date", label: "Newest incident" },
  { value: "incident_date", label: "Oldest incident" },
  { value: "-requested_amount", label: "Largest requested" },
  { value: "-leakage", label: "Largest leakage" },
  { value: "claim_id", label: "Claim ID" },
] as const;

export type ClaimSortValue = (typeof CLAIM_SORTS)[number]["value"];

export function parseClaimSort(value: string): ClaimSortValue {
  return CLAIM_SORTS.some((s) => s.value === value) ? (value as ClaimSortValue) : "-incident_date";
}
