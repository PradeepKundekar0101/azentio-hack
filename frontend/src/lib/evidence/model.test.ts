import { describe, expect, it } from "vitest";

import {
  decisionLabel,
  decisionTone,
  formatDelta,
  matchesFilter,
  relativeTime,
  reportUrl,
  shortHash,
} from "./model";

describe("matchesFilter", () => {
  it("groups the entries nobody typed under System", () => {
    expect(matchesFilter({ kind: "opened" }, "system")).toBe(true);
    expect(matchesFilter({ kind: "recalculated" }, "system")).toBe(true);
    expect(matchesFilter({ kind: "exported" }, "system")).toBe(true);
    expect(matchesFilter({ kind: "note" }, "system")).toBe(false);
  });

  it("matches one kind, or everything", () => {
    expect(matchesFilter({ kind: "override" }, "override")).toBe(true);
    expect(matchesFilter({ kind: "decision" }, "override")).toBe(false);
    expect(matchesFilter({ kind: "decision" }, "all")).toBe(true);
  });
});

describe("decisions", () => {
  it("names every review outcome, including escalation", () => {
    expect(decisionLabel("reviewed")).toBe("Confirmed discrepancy");
    expect(decisionLabel("dismissed")).toBe("False positive");
    expect(decisionLabel("escalated")).toBe("Escalated");
    expect(decisionLabel("sent_to_legal")).toBe("Sent to legal");
    expect(decisionLabel(null)).toBe("Not decided");
    expect(decisionTone("reviewed")).toBe("good");
    expect(decisionTone("evidence_requested")).toBe("warn");
  });
});

describe("shortHash", () => {
  it("keeps the start and end of a long hash", () => {
    expect(shortHash("0123456789abcdef0123456789abcdef")).toBe("01234567…cdef");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash(null)).toBe("–");
  });
});

describe("formatDelta", () => {
  it("signs rupee differences without float error", () => {
    expect(formatDelta("4500.00", "3000.00")).toBe("−₹1,500");
    expect(formatDelta("0.10", "0.30")).toBe("+₹0.20");
    expect(formatDelta("6000", "6000.00")).toBe("₹0");
    expect(formatDelta(null, "1")).toBe("–");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-10-31T12:00:00Z");

  it("reads like a person would say it", () => {
    expect(relativeTime("2026-10-31T11:59:40Z", now)).toBe("just now");
    expect(relativeTime("2026-10-31T11:55:00Z", now)).toBe("5 minutes ago");
    expect(relativeTime("2026-10-30T12:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("not a date", now)).toBe("–");
  });
});

describe("reportUrl", () => {
  it("encodes the claim ID", () => {
    expect(reportUrl("CLM-000001", "pdf")).toBe("/api/v1/evidence/claims/CLM-000001/report?format=pdf");
  });
});
