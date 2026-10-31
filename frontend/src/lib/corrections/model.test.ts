import { describe, expect, it } from "vitest";

import { correctionLabel, evidenceKind, reconciles, settlementSummary, splitCorrections, type CorrectionSetOut } from "./model";

const set = {
  requested_amount: "57294.00",
  recommended_payable: "34894.60",
  recovery_amount: null,
  corrections: [
    { correction_id: "COR-1", sequence: 1, type: "REMOVE_UNSUPPORTED_LINE", difference: "1200.00", applied: true, evidence_refs: ["DSC-1"] },
    { correction_id: "COR-2", sequence: 2, type: "ADJUST_TO_DOCUMENT", difference: "2500.00", applied: true, evidence_refs: ["DSC-2"] },
    { correction_id: "COR-3", sequence: 3, type: "APPLY_COPAY", difference: "18699.40", applied: true, evidence_refs: [] },
    { correction_id: "COR-4", sequence: 4, type: "REMOVE_UNSUPPORTED_LINE", difference: "9500.00", applied: false, evidence_refs: ["DSC-3"] },
    { correction_id: "COR-5", sequence: 5, type: "RECOVER_OVERPAYMENT", difference: "800.00", applied: true, evidence_refs: ["STL-1"] },
  ],
} as unknown as CorrectionSetOut;

describe("splitCorrections", () => {
  it("separates applied steps, items for review and the recovery", () => {
    const { applied, review, recovery } = splitCorrections(set);
    expect(applied.map((c) => c.correction_id)).toEqual(["COR-1", "COR-2", "COR-3"]);
    expect(review.map((c) => c.correction_id)).toEqual(["COR-4"]);
    expect(recovery?.correction_id).toBe("COR-5");
  });

  it("checks that requested minus the applied steps is the recommended payable", () => {
    expect(reconciles(set)).toBe(true);
    expect(reconciles({ ...set, recommended_payable: "34894.61" })).toBe(false);
  });
});

describe("labels", () => {
  it("names correction types and evidence kinds", () => {
    expect(correctionLabel("CAP_AT_SUB_LIMIT")).toBe("Cap at sub-limit");
    expect(correctionLabel("REDUCE_ROOM_DAYS")).toBe("Reduce room days");
    expect(evidenceKind("DSC-ABC")).toBe("Document discrepancy");
    expect(evidenceKind("REL-1")).toBe("Related claims");
    expect(evidenceKind("ALR-9")).toBe("Alert");
    expect(evidenceKind("STL-000001")).toBe("Settlement");
  });
});

describe("settlementSummary", () => {
  it("splits the reduction into document findings, policy limits and normal policy terms", () => {
    const demo = {
      ...set,
      corrections: [
        { type: "REMOVE_UNSUPPORTED_LINE", difference: "1200.00", applied: true },
        { type: "ADJUST_TO_DOCUMENT", difference: "2500.00", applied: true },
        { type: "REDUCE_ROOM_DAYS", difference: "12000.00", applied: true },
        { type: "CAP_AT_SUB_LIMIT", difference: "3000.00", applied: true },
        { type: "APPLY_DEDUCTIBLE", difference: "5000.00", applied: true },
        { type: "APPLY_COPAY", difference: "3359.40", applied: true },
      ],
    } as unknown as CorrectionSetOut;
    expect(settlementSummary(demo)).toEqual({ documents: "15700.00", policyLimits: "3000.00", policyTerms: "8359.40" });
  });
});
