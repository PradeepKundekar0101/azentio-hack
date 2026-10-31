import { describe, expect, it } from "vitest";

import {
  EMPTY,
  formatDate,
  formatDateTime,
  formatINR,
  formatINRCompact,
  formatNumber,
  formatPercent,
  groupIndian,
  toPaise,
} from "./format";

describe("groupIndian", () => {
  it.each([
    ["0", "0"],
    ["999", "999"],
    ["1000", "1,000"],
    ["99999", "99,999"],
    ["100000", "1,00,000"],
    ["1234567", "12,34,567"],
    ["123456789", "12,34,56,789"],
  ])("%s -> %s", (input, expected) => {
    expect(groupIndian(input)).toBe(expected);
  });
});

describe("toPaise", () => {
  it("parses decimal strings exactly", () => {
    expect(toPaise("142000.00")).toBe(BigInt(14200000));
    expect(toPaise("0.5")).toBe(BigInt(50));
    expect(toPaise("12")).toBe(BigInt(1200));
  });

  it("rounds half away from zero at the third decimal", () => {
    expect(toPaise("1.005")).toBe(BigInt(101));
    expect(toPaise("1.004")).toBe(BigInt(100));
    expect(toPaise("-1.005")).toBe(BigInt(-101));
  });

  it("handles amounts beyond float precision", () => {
    expect(toPaise("90071992547409931.99")).toBe(BigInt("9007199254740993199"));
  });

  it("rejects garbage", () => {
    expect(toPaise("abc")).toBeNull();
    expect(toPaise("")).toBeNull();
    expect(toPaise(Number.NaN)).toBeNull();
    expect(toPaise(null)).toBeNull();
  });
});

describe("formatINR", () => {
  it("formats API decimal strings with Indian grouping", () => {
    expect(formatINR("142000.00")).toBe("₹1,42,000");
    expect(formatINR("12345678.00")).toBe("₹1,23,45,678");
    expect(formatINR("999.00")).toBe("₹999");
    expect(formatINR("0.00")).toBe("₹0");
  });

  it("accepts numbers", () => {
    expect(formatINR(142000)).toBe("₹1,42,000");
    expect(formatINR(1500.75)).toBe("₹1,500.75");
  });

  it("shows paise only when non-zero", () => {
    expect(formatINR("1250.50")).toBe("₹1,250.50");
    expect(formatINR("1250.5")).toBe("₹1,250.50");
    expect(formatINR("1250.05")).toBe("₹1,250.05");
    expect(formatINR("1250.00")).toBe("₹1,250");
  });

  it("forces paise with the paise option", () => {
    expect(formatINR("1250", { paise: true })).toBe("₹1,250.00");
    expect(formatINR("142000.00", { paise: true })).toBe("₹1,42,000.00");
    expect(formatINR("142000.5", { paise: true })).toBe("₹1,42,000.50");
  });

  it("formats the room-rent example without paise", () => {
    // (₹7,000 − ₹5,000) × 3 = ₹6,000
    expect(formatINR("7000.00")).toBe("₹7,000");
    expect(formatINR("5000.00")).toBe("₹5,000");
    expect(formatINR("6000.00")).toBe("₹6,000");
  });

  it("formats negatives with a minus sign", () => {
    expect(formatINR("-4500.00")).toBe("−₹4,500");
    expect(formatINR("-0.004")).toBe("₹0");
  });

  it("signs positive amounts on request", () => {
    expect(formatINR("4500", { signed: true })).toBe("+₹4,500");
    expect(formatINR("0", { signed: true })).toBe("₹0");
  });

  it("ignores grouping commas and whitespace in input", () => {
    expect(formatINR(" 1,42,000.00 ")).toBe("₹1,42,000");
  });

  it("returns the empty marker for missing or invalid values", () => {
    expect(formatINR(null)).toBe(EMPTY);
    expect(formatINR(undefined)).toBe(EMPTY);
    expect(formatINR("n/a")).toBe(EMPTY);
  });
});

describe("formatINRCompact", () => {
  it.each([
    ["0.00", "₹0"],
    ["85000.00", "₹85,000"],
    ["99999.40", "₹99,999"],
    ["99999.60", "₹1 L"],
    ["100000.00", "₹1 L"],
    ["142000.00", "₹1.4 L"],
    ["1250000.00", "₹12.5 L"],
    ["9996000.00", "₹1 Cr"],
    ["23000000.00", "₹2.3 Cr"],
    ["125000000.00", "₹12.5 Cr"],
    ["12500000000.00", "₹1,250 Cr"],
    ["-142000.00", "−₹1.4 L"],
  ])("%s -> %s", (input, expected) => {
    expect(formatINRCompact(input)).toBe(expected);
  });

  it("supports more digits", () => {
    expect(formatINRCompact("142500.00", 2)).toBe("₹1.43 L");
  });

  it("returns the empty marker for invalid values", () => {
    expect(formatINRCompact("x")).toBe(EMPTY);
  });
});

describe("formatNumber", () => {
  it("uses Indian grouping", () => {
    expect(formatNumber(1234567)).toBe("12,34,567");
    expect(formatNumber(null)).toBe(EMPTY);
  });
});

describe("formatPercent", () => {
  it("formats ratios", () => {
    expect(formatPercent(0.234)).toBe("23.4%");
    expect(formatPercent("0.5", { digits: 0 })).toBe("50%");
  });

  it("formats percentage points", () => {
    expect(formatPercent(23.4, { ratio: false })).toBe("23.4%");
  });

  it("returns the empty marker for invalid values", () => {
    expect(formatPercent(null)).toBe(EMPTY);
    expect(formatPercent("abc")).toBe(EMPTY);
  });
});

describe("dates", () => {
  it("keeps date-only strings on their calendar day", () => {
    expect(formatDate("2026-03-12")).toBe("12 Mar 2026");
  });

  it("formats timestamps in India Standard Time", () => {
    expect(formatDate("2026-03-11T20:00:00Z")).toBe("12 Mar 2026");
    expect(formatDateTime("2026-03-12T08:35:00Z")).toBe("12 Mar 2026, 14:05");
  });

  it("returns the empty marker for missing or invalid values", () => {
    expect(formatDate(null)).toBe(EMPTY);
    expect(formatDate("not a date")).toBe(EMPTY);
    expect(formatDateTime(undefined)).toBe(EMPTY);
  });
});
