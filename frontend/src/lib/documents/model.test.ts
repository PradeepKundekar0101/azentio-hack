import { describe, expect, it } from "vitest";

import {
  alertCategoryLabel,
  checkDocumentFile,
  countErrors,
  draftToForm,
  emptyLine,
  formToPayload,
  humanizeMessage,
  lineProductMismatch,
  mapProblems,
  MAX_DOCUMENT_BYTES,
  paiseToAmount,
  parseStatusLabel,
  readExtracted,
  readProblems,
  sumLines,
} from "./model";

const extracted = {
  route: "vision",
  attempts: 2,
  extraction: { provider_name: "Greenleaf Multi Speciality Hosp." },
  draft: {
    claim: {
      policy_number: "POL-1001",
      claimant_id: null,
      claimant_name: "Ravi Kumar",
      incident_date: "2026-09-02",
      submission_date: "02/09/2026",
      claim_type: null,
      requested_amount: "12500.00",
      incident_reference: null,
    },
    invoice_reference: "INV-00452",
    provider_id: "PRV-0001",
    provider_name: "Greenleaf Multispeciality Hospital",
    provider_match_score: 91.4,
    lines: [
      {
        line_no: 1,
        service_date: "2026-09-02",
        service_code: "RM-PVT",
        service_description: "Private room",
        category: "room",
        quantity: "2",
        unit_price: "5000",
        line_amount: "10000",
        code_match: "description",
        code_confidence: 0.88,
      },
      {
        line_no: 2,
        service_date: null,
        service_code: null,
        service_description: "Misc charges",
        category: null,
        quantity: "1",
        unit_price: "2500",
        line_amount: "2500",
        code_match: "unresolved",
        code_confidence: 0,
      },
    ],
  },
};

describe("checkDocumentFile", () => {
  it("accepts PDF, PNG and JPEG", () => {
    for (const name of ["a.pdf", "b.PNG", "c.jpg", "d.jpeg"]) expect(checkDocumentFile({ name, size: 10 })).toBeNull();
  });

  it("rejects other types, empty and oversized files", () => {
    expect(checkDocumentFile({ name: "a.docx", size: 10 })).toMatch(/not a PDF, PNG or JPEG/);
    expect(checkDocumentFile({ name: "a.pdf", size: 0 })).toMatch(/empty/);
    expect(checkDocumentFile({ name: "a.pdf", size: MAX_DOCUMENT_BYTES + 1 })).toMatch(/larger than the 15\sMB limit/);
  });
});

describe("parseStatusLabel", () => {
  it.each([
    ["pending", "Reading"],
    ["needs_review", "Needs review"],
    ["confirmed", "Confirmed"],
    ["some_new_state", "Some new state"],
  ])("%s -> %s", (status, label) => expect(parseStatusLabel(status)).toBe(label));
});

describe("readExtracted", () => {
  it("reads route, attempts, the printed provider name and the draft", () => {
    const out = readExtracted(extracted);
    expect(out.route).toBe("vision");
    expect(out.attempts).toBe(2);
    expect(out.printedProviderName).toBe("Greenleaf Multi Speciality Hosp.");
    expect(out.draft?.lines).toHaveLength(2);
    expect(out.draft?.lines[1].code_match).toBe("unresolved");
    expect(out.draft?.provider_match_score).toBe(91.4);
  });

  it("tolerates missing or malformed data", () => {
    expect(readExtracted(null)).toEqual({ route: null, attempts: null, printedProviderName: null, draft: null });
    const out = readExtracted({ route: "ocr", draft: { claim: "x", lines: [null] } });
    expect(out.route).toBeNull();
    expect(out.draft?.claim.policy_number).toBeNull();
    expect(out.draft?.lines[0]).toMatchObject({ line_no: 1, code_match: "unresolved", quantity: null });
  });
});

describe("draftToForm and formToPayload", () => {
  const draft = readExtracted(extracted).draft!;

  it("prefills the form, leaving unresolved values empty", () => {
    const form = draftToForm(draft, new Set(["PRV-0001"]));
    expect(form.claim.policy_number).toBe("POL-1001");
    expect(form.claim.claimant_id).toBe("");
    // Not a YYYY-MM-DD date, so a date input could not show it.
    expect(form.claim.submission_date).toBe("");
    expect(form.provider_id).toBe("PRV-0001");
    expect(form.lines[0]).toMatchObject({ service_code: "RM-PVT", origin: "description", confidence: 0.88 });
    expect(form.lines[1]).toMatchObject({ service_code: "", category: "", service_date: "", origin: "unresolved" });
    expect(new Set(form.lines.map((l) => l.key)).size).toBe(2);
  });

  it("drops a provider that is not in the reference list", () => {
    expect(draftToForm(draft, new Set(["PRV-0002"])).provider_id).toBe("");
  });

  it("sends trimmed values, nulls for blanks and amounts without grouping", () => {
    const form = draftToForm(draft);
    form.claim.claim_type = "inpatient";
    form.claim.requested_amount = " ₹12,500.00 ";
    form.claim.claimant_name = "  Ravi Kumar ";
    form.lines.push({ ...emptyLine("2026-09-03"), service_code: "DX-CBC", unit_price: "1,200", line_amount: "1200" });
    const payload = formToPayload(form);
    expect(payload.claim).toEqual({
      policy_number: "POL-1001",
      claimant_id: null,
      claimant_name: "Ravi Kumar",
      incident_date: "2026-09-02",
      submission_date: null,
      claim_type: "inpatient",
      requested_amount: "12500.00",
      incident_reference: null,
    });
    expect(payload.invoice_reference).toBe("INV-00452");
    expect(payload.lines).toHaveLength(3);
    expect(payload.lines[1]).toEqual({
      service_date: null,
      service_code: null,
      service_description: "Misc charges",
      category: null,
      quantity: "1",
      unit_price: "2500",
      line_amount: "2500",
    });
    expect(payload.lines[2]).toMatchObject({ service_code: "DX-CBC", unit_price: "1200", quantity: "1" });
    expect(Object.keys(payload.lines[0])).not.toContain("key");
  });
});

describe("mapProblems", () => {
  const keys = ["line-a", "line-b"];

  it("puts claim, invoice and line problems next to their fields", () => {
    const problems = readProblems([
      { dataset: "claims", row: 1, field: "policy_number", code: "unknown_policy", message: "policy_number POL-9 does not exist" },
      { dataset: "claims", row: 1, field: "claim_type", code: "missing_field", message: "claim_type is required" },
      { dataset: "line_items", row: 2, field: "provider_id", code: "missing_field", message: "provider_id is required" },
      { dataset: "line_items", row: 3, field: "provider_id", code: "missing_field", message: "provider_id is required" },
      { dataset: "line_items", row: 3, field: "service_code", code: "missing_field", message: "service_code is required" },
      { dataset: "line_items", row: 2, field: "claim_id", code: "parent_rejected", message: "parent claim rejected: CLM-900001" },
    ]);
    const errors = mapProblems(problems, keys);
    expect(errors.claim).toEqual({
      policy_number: "Policy number POL-9 does not exist",
      claim_type: "Claim type is required",
    });
    expect(errors.invoice).toEqual({ provider_id: "Provider is required" });
    expect(errors.lines).toEqual({ "line-b": { service_code: "Service code is required" } });
    expect(errors.general).toEqual([]);
    expect(countErrors(errors)).toBe(4);
  });

  it("keeps problems without a known field as general messages", () => {
    const errors = mapProblems(
      readProblems([
        { dataset: "line_items", row: 2, field: "line_id", code: "id_exists", message: "line_id CLM-1-L01 already exists" },
        { dataset: "line_items", row: 9, field: "service_code", code: "x", message: "Odd row" },
        { dataset: "line_items", row: 2, field: "claim_id", code: "parent_rejected", message: "parent claim rejected" },
        { dataset: "claims", row: 1, field: null, code: "x", message: "Something about the claim" },
        "not a problem",
      ]),
      keys,
    );
    expect(errors.general).toEqual([
      "Line 1: Line ID CLM-1-L01 already exists",
      "Odd row",
      "Something about the claim",
    ]);
  });
});

describe("humanizeMessage", () => {
  it("replaces contract field names with labels", () => {
    expect(humanizeMessage("incident_date 2027-01-02 is in the future")).toBe("Incident date 2027-01-02 is in the future");
    expect(humanizeMessage("submission_date is before incident_date")).toBe("Submission date is before incident date");
    expect(humanizeMessage("unknown_thing stays")).toBe("Unknown_thing stays");
  });
});

describe("totals", () => {
  it("sums line amounts exactly and counts lines without one", () => {
    const out = sumLines([{ line_amount: "1000.10" }, { line_amount: "2,000.25" }, { line_amount: "" }, { line_amount: "abc" }]);
    expect(out.paise).toBe(BigInt(300035));
    expect(out.missing).toBe(2);
    expect(paiseToAmount(out.paise)).toBe("3000.35");
    expect(paiseToAmount(BigInt(-5))).toBe("-0.05");
  });

  it("flags quantity × unit price that differs from the amount", () => {
    expect(lineProductMismatch({ quantity: "3", unit_price: "1000", line_amount: "3000" })).toBeNull();
    expect(lineProductMismatch({ quantity: "1.5", unit_price: "2000", line_amount: "3000.00" })).toBeNull();
    expect(lineProductMismatch({ quantity: "3", unit_price: "1000", line_amount: "2500" })).toBe(BigInt(300000));
    expect(lineProductMismatch({ quantity: "", unit_price: "1000", line_amount: "2500" })).toBeNull();
  });
});

describe("alertCategoryLabel", () => {
  it("reads like a sentence", () => {
    expect(alertCategoryLabel("EXACT_DUPLICATE_CLAIM")).toBe("Exact duplicate claim");
  });
});
