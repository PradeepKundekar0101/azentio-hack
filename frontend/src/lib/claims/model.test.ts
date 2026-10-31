import { describe, expect, it } from "vitest";

import {
  affectedLineIds,
  type ClaimDetail,
  describeSignals,
  differingFields,
  formatScore,
  groupResults,
  type LineOut,
  outcomeTotals,
  type ResultOut,
  sourceRowLabel,
} from "./model";

function result(partial: Partial<ResultOut>): ResultOut {
  return {
    id: 1,
    check_code: "C01",
    check_name: "BENEFIT_PERIOD",
    line_id: null,
    policy_rule_id: null,
    outcome: "pass",
    expected: null,
    actual: null,
    amount_impact: "0.00",
    inputs: null,
    explanation: "",
    ...partial,
  };
}

function line(partial: Partial<LineOut>): LineOut {
  return {
    line_id: "LN-1",
    invoice_reference: "INV-1",
    provider_id: "PRV-0001",
    provider_name: "Greenleaf",
    service_date: "2026-04-11",
    service_code: "RM-GEN",
    service_description: "Room",
    category: "room",
    quantity: "1.00",
    unit_price: "100.00",
    line_amount: "100.00",
    source_row: null,
    ...partial,
  };
}

function claim(partial: Partial<ClaimDetail["claim"]>, lines: LineOut[]): ClaimDetail {
  return {
    claim: {
      claim_id: "CLM-1",
      policy_number: "POL-1",
      claimant_id: "MEM-1",
      claimant_name: "Ravi",
      incident_date: "2026-04-11",
      submission_date: "2026-04-15",
      claim_type: "inpatient",
      requested_amount: "26000.00",
      incident_reference: "ADM-1",
      status: "open",
      source: "file",
      import_batch_id: 1,
      source_row: null,
      ...partial,
    },
    policy: {} as ClaimDetail["policy"],
    lines,
    settlement: null,
    results: [],
    payable_steps: [],
    duplicates: [],
    alerts: [],
  };
}

describe("groupResults", () => {
  it("groups by check in code order and surfaces the most significant outcome", () => {
    const groups = groupResults([
      result({ id: 1, check_code: "C10", outcome: "adjusted" }),
      result({ id: 2, check_code: "C04", line_id: "LN-1", outcome: "pass" }),
      result({ id: 3, check_code: "C04", line_id: "LN-2", outcome: "fail" }),
      result({ id: 4, check_code: "C01", outcome: "pass" }),
      result({ id: 5, check_code: "C08", outcome: "not_applicable" }),
    ]);
    expect(groups.map((g) => g.code)).toEqual(["C01", "C04", "C08", "C10"]);
    expect(groups[1].outcome).toBe("fail");
    expect(groups[1].results.map((r) => r.id)).toEqual([2, 3]);
    expect(groups[1].counts).toEqual({ fail: 1, adjusted: 0, pass: 1, not_applicable: 0 });
    expect(groups[3].outcome).toBe("adjusted");
  });

  it("totals outcomes", () => {
    expect(
      outcomeTotals([result({ outcome: "pass" }), result({ outcome: "pass" }), result({ outcome: "fail" })]),
    ).toEqual({
      fail: 1,
      adjusted: 0,
      pass: 2,
      not_applicable: 0,
    });
  });
});

describe("sourceRowLabel", () => {
  it("names the file, sheet and row", () => {
    expect(sourceRowLabel({ file_name: "pack.xlsx", sheet: "Claims", row_number: 1204 })).toBe(
      "pack.xlsx · Claims · Row 1,204",
    );
    expect(sourceRowLabel({ file_name: "claims.csv", sheet: null, row_number: 2 })).toBe("claims.csv · Row 2");
    expect(sourceRowLabel(null)).toBeNull();
    expect(sourceRowLabel({ file_name: null, sheet: null, row_number: null })).toBeNull();
  });
});

describe("differingFields", () => {
  it("compares header fields, amounts exactly and line summaries as sets", () => {
    const a = claim({ claim_id: "CLM-2", incident_date: "2026-04-13", requested_amount: "26400.00" }, [
      line({ invoice_reference: "INV452A", service_code: "RM-GEN" }),
      line({ invoice_reference: "INV452A", service_code: "PRC-ENDO" }),
    ]);
    const b = claim({ requested_amount: "26400" }, [
      line({ invoice_reference: "INV-00452", service_code: "PRC-ENDO" }),
      line({ invoice_reference: "INV-00452", service_code: "RM-GEN" }),
    ]);
    const diff = differingFields(a, b);
    expect(diff.has("incident_date")).toBe(true);
    expect(diff.has("requested_amount")).toBe(false);
    expect(diff.has("invoices")).toBe(true);
    expect(diff.has("services")).toBe(false);
    expect(diff.has("providers")).toBe(false);
    expect(diff.has("claimant_name")).toBe(false);
  });
});

describe("affectedLineIds", () => {
  it("joins the alert line with supporting line IDs", () => {
    expect([...affectedLineIds({ line_id: "LN-1", supporting: { line_ids: ["LN-1", "LN-2", 3] } })]).toEqual([
      "LN-1",
      "LN-2",
    ]);
    expect(affectedLineIds({ line_id: null, supporting: {} }).size).toBe(0);
  });
});

describe("describeSignals", () => {
  it("formats near-duplicate signals in a fixed order", () => {
    const rows = describeSignals({
      excess_frequency: false,
      same_provider: true,
      overlapping_amount: "26400.00",
      amount_difference: "0.015",
      date_gap_days: 2,
      reference_similarity: "0.92",
      references: [["INV452A"], ["INV452"]],
      code_overlap: "1.00",
    });
    expect(rows.map((r) => r.key)).toEqual([
      "reference_similarity",
      "date_gap_days",
      "amount_difference",
      "code_overlap",
      "same_provider",
      "references",
      "overlapping_amount",
      "excess_frequency",
    ]);
    expect(rows.find((r) => r.key === "amount_difference")?.value).toBe("1.50%");
    expect(rows.find((r) => r.key === "date_gap_days")?.value).toBe("2 days");
    expect(rows.find((r) => r.key === "references")?.value).toBe("INV452A vs INV452");
    expect(rows.find((r) => r.key === "overlapping_amount")?.value).toBe("₹26,400");
    expect(rows.find((r) => r.key === "same_provider")?.value).toBe("Yes");
    expect(describeSignals(null)).toEqual([]);
  });

  it("formats scores to two places", () => {
    expect(formatScore("0.8900")).toBe("0.89");
    expect(formatScore(null)).toBe("–");
  });
});
