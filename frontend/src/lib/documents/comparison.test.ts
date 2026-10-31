import { describe, expect, it } from "vitest";

import {
  comparisonRows,
  discrepancyLabel,
  type ComparisonOut,
  type ExtractionOut,
  headerRows,
  type ClaimLine,
} from "./comparison";

const claimLines = [
  { line_id: "LN-1", invoice_reference: "INV-452", provider_name: "Apollo", service_date: "2026-03-10", service_code: "PRC-HERN", service_description: "Inguinal hernia repair", quantity: "1", unit_price: "12000.00", line_amount: "12000.00" },
  { line_id: "LN-2", invoice_reference: "INV-452", provider_name: "Apollo", service_date: "2026-03-10", service_code: "OTH-AMB", service_description: "Ambulance charges", quantity: "1", unit_price: "1200.00", line_amount: "1200.00" },
] as ClaimLine[];

const box = { l: 0.1, t: 0.3, r: 0.9, b: 0.32 };
const field = (path: string, value: string | null, status = "verified") => ({
  field_path: path, value_text: value, value_normalised: value, page: 1, bbox: status === "verified" ? box : null,
  source_quote: value, provenance_status: status, confidence: "1.000",
});

const extraction = {
  extraction_id: 9, document_id: 4, version: 1, doc_type: "invoice", status: "ok",
  fields: [field("header.invoice_number", "INV-452"), field("header.patient_name", "Ravi Kumar"), field("header.total", "9500.00")],
  lines: [{ line_no: 1, description: "Inguinal hernia repair", service_code: "PRC-HERN", service_date: "2026-03-10", quantity: "1", unit_price: "9500.00", amount: "9500.00", page: 1, bbox: box }],
} as unknown as ExtractionOut;

const comparison = {
  comparison_id: 3, version: 1, doc_type: "invoice",
  line_matches: {
    pairs: [{ claim_line_id: "LN-1", document_line_no: 1, similarity: 0.8, generated_by: "rule" }],
    unmatched_claim: ["LN-2"],
    unmatched_document: [],
  },
  discrepancies: [
    { discrepancy_id: "DSC-A", type: "AMOUNT_MISMATCH", amount_impact: "2500.00", amount_type: "calculated", claim_ref: { line_id: "LN-1" }, document_ref: { page: 1, bbox: box, line_no: 1 } },
    { discrepancy_id: "DSC-B", type: "ONLY_IN_CLAIM", amount_impact: "1200.00", amount_type: "calculated", claim_ref: { line_id: "LN-2" }, document_ref: { page: 1, bbox: null, line_no: null } },
    { discrepancy_id: "DSC-C", type: "TOTAL_MISMATCH", amount_impact: null, amount_type: null, claim_ref: { line_id: null }, document_ref: { page: 1, bbox: box, line_no: null } },
  ],
} as unknown as ComparisonOut;

describe("comparisonRows", () => {
  const rows = comparisonRows(comparison, claimLines, extraction);

  it("pairs claim and document lines and marks the values that differ", () => {
    const pair = rows.find((r) => r.kind === "pair")!;
    expect(pair.claim?.line_id).toBe("LN-1");
    expect(pair.doc?.line_no).toBe(1);
    expect(pair.differs).toEqual(["unit_price", "amount"]);
    expect(pair.discrepancies.map((d) => d.discrepancy_id)).toEqual(["DSC-A"]);
    expect(pair.target).toEqual({ page: 1, bbox: box });
  });

  it("lists unmatched claim lines with their discrepancy and no place on the page", () => {
    const only = rows.find((r) => r.kind === "claim_only")!;
    expect(only.claim?.line_id).toBe("LN-2");
    expect(only.doc).toBeNull();
    expect(only.discrepancies.map((d) => d.type)).toEqual(["ONLY_IN_CLAIM"]);
    expect(only.target).toBeNull();
  });
});

describe("headerRows", () => {
  it("puts the claim's values beside the document's, with where each was printed", () => {
    const rows = headerRows(extraction, { claimant_name: "Ravi Kumar", incident_date: "2026-03-10" }, claimLines);
    const total = rows.find((r) => r.key === "total")!;
    expect([total.claimValue, total.documentValue, total.differs]).toEqual(["13200.00", "9500.00", true]);
    expect(total.target).toEqual({ page: 1, bbox: box });
    const number = rows.find((r) => r.key === "invoice_number")!;
    expect(number.differs).toBe(false);
    expect(rows.find((r) => r.key === "patient_name")!.differs).toBe(false);
  });
});

describe("discrepancyLabel", () => {
  it("names every discrepancy type", () => {
    expect(discrepancyLabel("STAY_LENGTH_MISMATCH")).toBe("Stay shorter than billed");
    expect(discrepancyLabel("ONLY_IN_CLAIM")).toBe("Not on the invoice");
    expect(discrepancyLabel("SOMETHING_NEW")).toBe("Something new");
  });
});
