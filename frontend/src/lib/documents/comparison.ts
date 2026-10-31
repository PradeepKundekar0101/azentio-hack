/**
 * Pure helpers for the document comparison view: claim lines beside the document lines they were matched to, the
 * values that differ, the header fields side by side, and where on the page each value was printed.
 */
import type { Schemas } from "@/lib/api/client";

import { toPaise } from "../format";

export type DocumentComparisonOut = Schemas["DocumentComparisonOut"];
export type ComparisonOut = Schemas["ComparisonOut"];
export type DiscrepancyOut = Schemas["DiscrepancyOut"];
export type ExtractionOut = Schemas["ExtractionOut"];
export type FieldOut = Schemas["FieldOut"];
export type ExtractedLineOut = Schemas["ExtractedLineOut"];
export type ClaimLine = Pick<
  Schemas["LineOut"],
  | "line_id"
  | "invoice_reference"
  | "provider_name"
  | "service_date"
  | "service_code"
  | "service_description"
  | "quantity"
  | "unit_price"
  | "line_amount"
>;

export interface Box {
  l: number;
  t: number;
  r: number;
  b: number;
}

export interface Target {
  page: number;
  bbox: Box | null;
}

export interface LineRow {
  key: string;
  kind: "pair" | "claim_only" | "doc_only";
  claim: ClaimLine | null;
  doc: ExtractedLineOut | null;
  differs: ("quantity" | "unit_price" | "amount" | "service_date")[];
  discrepancies: DiscrepancyOut[];
  target: Target | null;
  aiMatch: boolean;
}

interface MatchPair {
  claim_line_id: string;
  document_line_no: number;
  generated_by?: string;
}

const sameAmount = (a: unknown, b: unknown) => toPaise(a as string) === toPaise(b as string);

function target(page: number | null | undefined, bbox: unknown): Target | null {
  return page ? { page, bbox: (bbox as Box | null) ?? null } : null;
}

export function comparisonRows(comparison: ComparisonOut, claimLines: ClaimLine[], extraction: ExtractionOut): LineRow[] {
  const matches = comparison.line_matches as {
    pairs?: MatchPair[];
    unmatched_claim?: string[];
    unmatched_document?: number[];
  };
  const claimById = new Map(claimLines.map((line) => [line.line_id, line]));
  const docByNo = new Map(extraction.lines.map((line) => [line.line_no, line]));
  const forLine = (lineId: string | null, lineNo: number | null) =>
    comparison.discrepancies.filter((d) => {
      const claimRef = d.claim_ref as { line_id?: string | null };
      const docRef = d.document_ref as { line_no?: number | null };
      return (lineId !== null && claimRef.line_id === lineId) || (lineNo !== null && docRef.line_no === lineNo && !claimRef.line_id);
    });
  const rows: LineRow[] = [];
  for (const pair of matches.pairs ?? []) {
    const claim = claimById.get(pair.claim_line_id) ?? null;
    const doc = docByNo.get(pair.document_line_no) ?? null;
    if (!claim || !doc) continue;
    const differs: LineRow["differs"] = [];
    if (doc.quantity != null && Number(doc.quantity) !== Number(claim.quantity)) differs.push("quantity");
    if (doc.unit_price != null && !sameAmount(doc.unit_price, claim.unit_price)) differs.push("unit_price");
    if (doc.amount != null && !sameAmount(doc.amount, claim.line_amount)) differs.push("amount");
    if (doc.service_date && doc.service_date !== claim.service_date) differs.push("service_date");
    rows.push({
      key: `pair:${claim.line_id}`,
      kind: "pair",
      claim,
      doc,
      differs,
      discrepancies: forLine(claim.line_id, null),
      target: target(doc.page, doc.bbox),
      aiMatch: pair.generated_by === "ai",
    });
  }
  for (const lineId of matches.unmatched_claim ?? []) {
    const claim = claimById.get(lineId) ?? null;
    if (!claim) continue;
    rows.push({
      key: `claim:${lineId}`,
      kind: "claim_only",
      claim,
      doc: null,
      differs: [],
      discrepancies: forLine(lineId, null),
      target: null,
      aiMatch: false,
    });
  }
  for (const lineNo of matches.unmatched_document ?? []) {
    const doc = docByNo.get(lineNo) ?? null;
    if (!doc) continue;
    rows.push({
      key: `doc:${lineNo}`,
      kind: "doc_only",
      claim: null,
      doc,
      differs: [],
      discrepancies: forLine(null, lineNo),
      target: target(doc.page, doc.bbox),
      aiMatch: false,
    });
  }
  return rows;
}

export interface HeaderRow {
  key: string;
  label: string;
  claimValue: string | null;
  documentValue: string | null;
  differs: boolean;
  provenance: string | null;
  target: Target | null;
}

function fieldAt(extraction: ExtractionOut, path: string): FieldOut | undefined {
  return extraction.fields.find((f) => f.field_path === path);
}

const norm = (value: string | null | undefined) => (value ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "").replace(/(?<![0-9])0+(?=[0-9])/g, "");
const sameName = (a: string | null, b: string | null) =>
  (a ?? "").toLowerCase().replace(/\s+/g, " ").trim() === (b ?? "").toLowerCase().replace(/\s+/g, " ").trim();

function row(extraction: ExtractionOut, key: string, label: string, claimValue: string | null, differs: (doc: string | null) => boolean): HeaderRow {
  const field = fieldAt(extraction, `header.${key}`);
  const documentValue = field?.value_normalised ?? null;
  return {
    key,
    label,
    claimValue,
    documentValue,
    differs: documentValue !== null && claimValue !== null && differs(documentValue),
    provenance: field?.provenance_status ?? null,
    target: field ? target(field.page, field.bbox) : null,
  };
}

/** The document's header beside the claim: for an invoice its number, patient, dates and total. */
export function headerRows(
  extraction: ExtractionOut,
  claim: { claimant_name: string; incident_date: string },
  claimLines: ClaimLine[],
): HeaderRow[] {
  if (extraction.doc_type === "discharge_summary") {
    return [
      row(extraction, "patient_name", "Patient", claim.claimant_name, (doc) => !sameName(doc, claim.claimant_name)),
      row(extraction, "admission_date", "Admission", claim.incident_date, (doc) => doc !== claim.incident_date),
      row(extraction, "discharge_date", "Discharge", null, () => false),
      row(extraction, "diagnosis", "Diagnosis", null, () => false),
    ];
  }
  const refs = [...new Set(claimLines.map((line) => line.invoice_reference))];
  const number = fieldAt(extraction, "header.invoice_number")?.value_normalised ?? null;
  const onInvoice = claimLines.filter((line) => norm(line.invoice_reference) === norm(number));
  const lines = onInvoice.length > 0 ? onInvoice : claimLines;
  const paise = lines.reduce((sum, line) => sum + (toPaise(line.line_amount) ?? BigInt(0)), BigInt(0));
  const total = `${paise / BigInt(100)}.${(paise % BigInt(100)).toString().padStart(2, "0")}`;
  return [
    row(extraction, "invoice_number", "Invoice number", refs.join(", "), (doc) => !refs.some((ref) => norm(ref) === norm(doc))),
    row(extraction, "patient_name", "Patient", claim.claimant_name, (doc) => !sameName(doc, claim.claimant_name)),
    row(extraction, "provider_name", "Provider", lines[0]?.provider_name ?? null, () => false),
    row(extraction, "admission_date", "Visit or admission", claim.incident_date, (doc) => doc !== claim.incident_date),
    row(extraction, "total", "Total", total, (doc) => !sameAmount(doc, total)),
  ];
}

const LABELS: Record<string, string> = {
  INVOICE_REF_MISMATCH: "Invoice number differs",
  PROVIDER_MISMATCH: "Provider differs",
  PATIENT_MISMATCH: "Patient differs",
  DATE_MISMATCH: "Dates differ",
  TOTAL_MISMATCH: "Total differs",
  AMOUNT_MISMATCH: "Amount higher than invoice",
  QUANTITY_MISMATCH: "Quantity differs",
  UNIT_PRICE_MISMATCH: "Unit price differs",
  SERVICE_DATE_MISMATCH: "Service date differs",
  ONLY_IN_CLAIM: "Not on the invoice",
  ONLY_IN_DOCUMENT: "Not claimed",
  STAY_LENGTH_MISMATCH: "Stay shorter than billed",
  PROCEDURE_NOT_DOCUMENTED: "Procedure not documented",
};

export function discrepancyLabel(type: string): string {
  if (LABELS[type]) return LABELS[type];
  const words = type.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
