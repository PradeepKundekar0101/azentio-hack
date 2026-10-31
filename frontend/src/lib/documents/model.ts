/**
 * Pure helpers for the Documents pages: upload checks, parse status, reading the extraction
 * draft, the review form and its confirm payload, server validation errors mapped back to
 * form fields, and line totals. No React or network code here, so it is unit tested directly.
 */
import type { Schemas } from "@/lib/api/client";

import { formatBytes, toPaise } from "../format";

export type DocumentRow = Schemas["DocumentOut"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type ConfirmPayload = Schemas["ConfirmIn"];
export type ConfirmResult = Schemas["ConfirmOut"];
export type Run = Schemas["RunOut"];
export type Provider = Schemas["ProviderOut"];
export type ServiceCode = Schemas["ServiceCodeOut"];

// ---------------------------------------------------------------------------------------
// Upload

/** Matches MAX_DOCUMENT_BYTES in backend/app/api/documents.py. */
export const MAX_DOCUMENT_BYTES = 15 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"] as const;
export const ACCEPT_ATTRIBUTE = [...ACCEPTED_EXTENSIONS, "application/pdf", "image/png", "image/jpeg"].join(",");

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

/**
 * Why a file cannot be uploaded, or null when it can. The backend checks the real type from
 * the file's bytes too; this catches the obvious cases before any upload.
 */
export function checkDocumentFile(file: Pick<File, "name" | "size">): string | null {
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(file.name))) {
    return `${file.name} is not a PDF, PNG or JPEG file.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > MAX_DOCUMENT_BYTES) {
    return `${file.name} is larger than the ${formatBytes(MAX_DOCUMENT_BYTES)} limit.`;
  }
  return null;
}

// ---------------------------------------------------------------------------------------
// Parse status

export type ParseStatus = "pending" | "extracted" | "needs_review" | "failed" | "confirmed";

export const PARSE_STATUS_LABELS: Record<ParseStatus, string> = {
  pending: "Reading",
  extracted: "Ready for review",
  needs_review: "Needs review",
  failed: "Failed",
  confirmed: "Confirmed",
};

export function parseStatusLabel(status: string): string {
  if (status in PARSE_STATUS_LABELS) return PARSE_STATUS_LABELS[status as ParseStatus];
  const words = status.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The backend is still reading the document. */
export function isReading(status: string): boolean {
  return status === "pending";
}

/** A draft can be reviewed and confirmed. */
export function isReviewable(status: string): boolean {
  return status === "extracted" || status === "needs_review";
}

export function fileKind(fileType: string): "pdf" | "image" {
  return fileType === "pdf" ? "pdf" : "image";
}

// ---------------------------------------------------------------------------------------
// The extraction draft (DocumentDetail.extracted), read defensively: it is free-form JSON.

export type CodeMatch = "printed_code" | "description" | "unresolved";

export interface DraftLine {
  line_no: number;
  service_date: string | null;
  service_code: string | null;
  service_description: string | null;
  category: string | null;
  quantity: string | null;
  unit_price: string | null;
  line_amount: string | null;
  code_match: CodeMatch;
  code_confidence: number | null;
}

export const CLAIM_FIELDS = [
  "policy_number",
  "claimant_id",
  "claimant_name",
  "incident_date",
  "submission_date",
  "claim_type",
  "requested_amount",
  "incident_reference",
] as const;
export type ClaimField = (typeof CLAIM_FIELDS)[number];

export const LINE_FIELDS = [
  "service_date",
  "service_code",
  "service_description",
  "category",
  "quantity",
  "unit_price",
  "line_amount",
] as const;
export type LineField = (typeof LINE_FIELDS)[number];

/** Form fields outside the claim and lines: shared by every line in the import contract. */
export const INVOICE_FIELDS = ["invoice_reference", "provider_id", "provider_name"] as const;
export type InvoiceField = (typeof INVOICE_FIELDS)[number];

export interface Draft {
  claim: Record<ClaimField, string | null>;
  invoice_reference: string | null;
  provider_id: string | null;
  provider_name: string | null;
  provider_match_score: number | null;
  lines: DraftLine[];
}

export interface Extracted {
  route: "text" | "vision" | null;
  attempts: number | null;
  /** The provider name as printed on the invoice, before matching. */
  printedProviderName: string | null;
  draft: Draft | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Strings stay strings; numbers become their text; anything else, or a blank string, is null. */
function text(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function num(value: unknown): number | null {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function readLine(value: unknown, index: number): DraftLine {
  const line = isRecord(value) ? value : {};
  const match = line.code_match;
  return {
    line_no: num(line.line_no) ?? index + 1,
    service_date: text(line.service_date),
    service_code: text(line.service_code),
    service_description: text(line.service_description),
    category: text(line.category),
    quantity: text(line.quantity),
    unit_price: text(line.unit_price),
    line_amount: text(line.line_amount),
    code_match: match === "printed_code" || match === "description" ? match : "unresolved",
    code_confidence: num(line.code_confidence),
  };
}

function readDraft(value: unknown): Draft | null {
  if (!isRecord(value)) return null;
  const claim = isRecord(value.claim) ? value.claim : {};
  return {
    claim: Object.fromEntries(CLAIM_FIELDS.map((f) => [f, text(claim[f])])) as Record<ClaimField, string | null>,
    invoice_reference: text(value.invoice_reference),
    provider_id: text(value.provider_id),
    provider_name: text(value.provider_name),
    provider_match_score: num(value.provider_match_score),
    lines: Array.isArray(value.lines) ? value.lines.map(readLine) : [],
  };
}

export function readExtracted(extracted: unknown): Extracted {
  if (!isRecord(extracted)) return { route: null, attempts: null, printedProviderName: null, draft: null };
  const route = extracted.route === "text" || extracted.route === "vision" ? extracted.route : null;
  const extraction = isRecord(extracted.extraction) ? extracted.extraction : {};
  return {
    route,
    attempts: num(extracted.attempts),
    printedProviderName: text(extraction.provider_name),
    draft: readDraft(extracted.draft),
  };
}

// ---------------------------------------------------------------------------------------
// Reference values

export const CLAIM_TYPES = ["inpatient", "outpatient", "daycare", "pharmacy", "diagnostics"] as const;
export const CATEGORIES = [
  "room",
  "icu",
  "consultation",
  "procedure",
  "pharmacy",
  "diagnostics",
  "consumables",
  "physiotherapy",
  "other",
] as const;

const LABEL_OVERRIDES: Record<string, string> = { icu: "ICU", daycare: "Day care" };

/** "inpatient" -> "Inpatient", "icu" -> "ICU". */
export function optionLabel(value: string): string {
  if (LABEL_OVERRIDES[value]) return LABEL_OVERRIDES[value];
  const words = value.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// ---------------------------------------------------------------------------------------
// Review form state

/** How the line's service code was set: from the extraction, or chosen by the reviewer. */
export type LineOrigin = CodeMatch | "manual";

export interface FormLine extends Record<LineField, string> {
  /** Stable key for React lists and error mapping; never sent. */
  key: string;
  origin: LineOrigin;
  confidence: number | null;
}

export interface ReviewForm extends Record<InvoiceField, string> {
  claim: Record<ClaimField, string>;
  lines: FormLine[];
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** A YYYY-MM-DD date for a date input, or "" when the draft value is not one. */
function isoDate(value: string | null): string {
  if (!value || !ISO_DATE_RE.test(value)) return "";
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== value ? "" : value;
}

const DATE_FIELDS = new Set<string>(["incident_date", "submission_date", "service_date"]);

function formValue(field: string, value: string | null): string {
  if (DATE_FIELDS.has(field)) return isoDate(value);
  return value ?? "";
}

let lineCounter = 0;
export function newLineKey(): string {
  lineCounter += 1;
  return `line-${lineCounter}`;
}

export function emptyLine(serviceDate = ""): FormLine {
  return {
    key: newLineKey(),
    origin: "manual",
    confidence: null,
    service_date: serviceDate,
    service_code: "",
    service_description: "",
    category: "",
    quantity: "1",
    unit_price: "",
    line_amount: "",
  };
}

/**
 * The editable form, prefilled from the draft. Unresolved values become empty strings for the
 * reviewer to fill. Only values the inputs can hold are kept (a select cannot show a value
 * outside its options), so nothing invisible is sent back.
 */
export function draftToForm(draft: Draft, providerIds?: ReadonlySet<string>): ReviewForm {
  const claim = Object.fromEntries(CLAIM_FIELDS.map((f) => [f, formValue(f, draft.claim[f])])) as Record<
    ClaimField,
    string
  >;
  if (claim.claim_type && !(CLAIM_TYPES as readonly string[]).includes(claim.claim_type)) claim.claim_type = "";
  const providerId =
    draft.provider_id && (!providerIds || providerIds.has(draft.provider_id)) ? draft.provider_id : "";
  return {
    claim,
    invoice_reference: draft.invoice_reference ?? "",
    provider_id: providerId,
    provider_name: draft.provider_name ?? "",
    lines: draft.lines.map((line) => ({
      key: newLineKey(),
      origin: line.service_code ? line.code_match : "unresolved",
      confidence: line.code_confidence,
      service_date: isoDate(line.service_date),
      service_code: line.service_code ?? "",
      service_description: line.service_description ?? "",
      category:
        line.category && (CATEGORIES as readonly string[]).includes(line.category) ? line.category : "",
      quantity: line.quantity ?? "",
      unit_price: line.unit_price ?? "",
      line_amount: line.line_amount ?? "",
    })),
  };
}

/** Trims text and strips digit grouping from amounts. Empty values are sent as null. */
function clean(value: string, amount = false): string | null {
  let out = value.trim();
  if (amount) out = out.replace(/[,\s₹]/g, "");
  return out ? out : null;
}

const AMOUNT_FIELDS = new Set<string>(["requested_amount", "quantity", "unit_price", "line_amount"]);

export function formToPayload(form: ReviewForm): ConfirmPayload {
  const claim = Object.fromEntries(
    CLAIM_FIELDS.map((f) => [f, clean(form.claim[f], AMOUNT_FIELDS.has(f))]),
  ) as ConfirmPayload["claim"];
  return {
    claim,
    invoice_reference: clean(form.invoice_reference),
    provider_id: clean(form.provider_id),
    provider_name: clean(form.provider_name),
    lines: form.lines.map(
      (line) => Object.fromEntries(LINE_FIELDS.map((f) => [f, clean(line[f], AMOUNT_FIELDS.has(f))])) as ConfirmPayload["lines"][number],
    ),
  };
}

// ---------------------------------------------------------------------------------------
// Server validation errors (422 validation_failed) mapped onto the form

export interface ValidationProblem {
  dataset: string;
  row: number | null;
  field: string | null;
  code: string;
  message: string;
}

export interface FormErrors {
  claim: Partial<Record<ClaimField, string>>;
  invoice: Partial<Record<InvoiceField, string>>;
  /** By line key. */
  lines: Record<string, Partial<Record<LineField, string>>>;
  /** Problems that belong to no single field. */
  general: string[];
}

export function emptyErrors(): FormErrors {
  return { claim: {}, invoice: {}, lines: {}, general: [] };
}

export function countErrors(errors: FormErrors): number {
  return (
    Object.keys(errors.claim).length +
    Object.keys(errors.invoice).length +
    Object.values(errors.lines).reduce((n, line) => n + Object.keys(line).length, 0) +
    errors.general.length
  );
}

export function readProblems(details: unknown): ValidationProblem[] {
  if (!Array.isArray(details)) return [];
  return details.filter(isRecord).map((d) => ({
    dataset: typeof d.dataset === "string" ? d.dataset : "",
    row: typeof d.row === "number" ? d.row : null,
    field: typeof d.field === "string" && d.field ? d.field : null,
    code: typeof d.code === "string" ? d.code : "",
    message: typeof d.message === "string" ? d.message : "This value is not valid.",
  }));
}

export const FIELD_LABELS: Record<string, string> = {
  policy_number: "Policy number",
  claimant_id: "Claimant ID",
  claimant_name: "Claimant name",
  incident_date: "Incident date",
  submission_date: "Submission date",
  claim_type: "Claim type",
  requested_amount: "Requested amount",
  incident_reference: "Incident reference",
  invoice_reference: "Invoice reference",
  provider_id: "Provider",
  provider_name: "Provider name",
  service_date: "Service date",
  service_code: "Service code",
  service_description: "Description",
  category: "Category",
  quantity: "Quantity",
  unit_price: "Unit price",
  line_amount: "Amount",
  claim_id: "Claim ID",
  line_id: "Line ID",
};

/**
 * Validation messages name fields the way the import contract does ("incident_date 2027-01-02
 * is in the future"). Field names become labels so they read naturally next to the field.
 */
export function humanizeMessage(message: string): string {
  const out = message.replace(/\b[a-z]+(?:_[a-z]+)+\b/g, (word) => {
    const label = FIELD_LABELS[word];
    return label ? label.charAt(0).toLowerCase() + label.slice(1) : word;
  });
  return out.charAt(0).toUpperCase() + out.slice(1);
}

/**
 * Places each problem next to its field. Row 1 of the claims dataset is the claim; line items
 * are rows 2..n+1 in line order. Invoice and provider fields repeat on every line, so they are
 * shown once at the top. A line rejected only because the claim was rejected adds nothing the
 * claim's own errors do not already say.
 */
export function mapProblems(problems: ValidationProblem[], lineKeys: string[]): FormErrors {
  const errors = emptyErrors();
  const claimRejected = problems.some((p) => p.dataset === "claims");
  const general = new Set<string>();

  for (const p of problems) {
    const message = humanizeMessage(p.message);
    const field = p.field;
    if (p.dataset === "claims" && field && (CLAIM_FIELDS as readonly string[]).includes(field)) {
      errors.claim[field as ClaimField] ??= message;
      continue;
    }
    if (p.dataset === "line_items") {
      if (p.code === "parent_rejected" && claimRejected) continue;
      if (field && (INVOICE_FIELDS as readonly string[]).includes(field)) {
        errors.invoice[field as InvoiceField] ??= message;
        continue;
      }
      const key = p.row !== null ? lineKeys[p.row - 2] : undefined;
      if (key && field && (LINE_FIELDS as readonly string[]).includes(field)) {
        const line = (errors.lines[key] ??= {});
        line[field as LineField] ??= message;
        continue;
      }
      if (key) {
        general.add(`Line ${p.row! - 1}: ${message}`);
        continue;
      }
    }
    general.add(message);
  }
  errors.general = [...general];
  return errors;
}

// ---------------------------------------------------------------------------------------
// Totals

/** Sum of line amounts in paise; lines with no valid amount are counted separately. */
export function sumLines(lines: Pick<FormLine, "line_amount">[]): { paise: bigint; missing: number } {
  let paise = BigInt(0);
  let missing = 0;
  for (const line of lines) {
    const value = toPaise(line.line_amount.trim() || null);
    if (value === null) missing += 1;
    else paise += value;
  }
  return { paise, missing };
}

/** Paise back to a decimal string ("1234.50") for formatINR. */
export function paiseToAmount(paise: bigint): string {
  const negative = paise < BigInt(0);
  const abs = negative ? -paise : paise;
  const rupees = abs / BigInt(100);
  const rem = (abs % BigInt(100)).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${rupees}.${rem}`;
}

/** Same ±₹1 tolerance the backend uses for the invoice total. */
export const TOTAL_TOLERANCE_PAISE = BigInt(100);

/**
 * Quantity × unit price in paise when both are numbers and it differs from the amount by more
 * than a paisa, else null. Quantities may be fractional (e.g. 1.5 days).
 */
export function lineProductMismatch(line: Pick<FormLine, "quantity" | "unit_price" | "line_amount">): bigint | null {
  const qty = Number(line.quantity.trim().replace(/,/g, ""));
  const unit = toPaise(line.unit_price.trim() || null);
  const amount = toPaise(line.line_amount.trim() || null);
  if (!line.quantity.trim() || !Number.isFinite(qty) || unit === null || amount === null) return null;
  const product = BigInt(Math.round(qty * Number(unit)));
  const diff = product - amount;
  return diff > BigInt(1) || diff < BigInt(-1) ? product : null;
}

// ---------------------------------------------------------------------------------------
// Alerts raised on the confirmed claim

/** "EXACT_DUPLICATE_CLAIM" -> "Exact duplicate claim". */
export function alertCategoryLabel(category: string): string {
  const words = category.toLowerCase().replace(/_+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
