import { describe, expect, it } from "vitest";

import {
  countActiveFilters,
  EMPTY_FILTERS,
  filtersToApiQuery,
  filtersToSearch,
  filtersToUrlPatch,
  nextSort,
  parseAlertFilters,
  parseAmount,
  parseIsoDate,
  parseSort,
  rangeProblems,
  sortState,
} from "./filters";
import { checkName, describePattern, severityRank } from "./model";

describe("parseAlertFilters", () => {
  it("reads comma lists, amounts and dates from search params", () => {
    const params = new URLSearchParams(
      "category=NOT_COVERED,EXCLUDED_SERVICE&severity=high&provider_id=PRV-0001,PRV-0002&amount_min=5000&amount_max=2500.50&date_from=2026-01-01&date_to=2026-03-31&status=open&amount_type=calculated&claim_type=inpatient",
    );
    expect(parseAlertFilters(params)).toEqual({
      claim_type: ["inpatient"],
      provider_id: ["PRV-0001", "PRV-0002"],
      category: ["NOT_COVERED", "EXCLUDED_SERVICE"],
      severity: ["high"],
      amount_type: ["calculated"],
      status: ["open"],
      amount_min: "5000",
      amount_max: "2500.50",
      date_from: "2026-01-01",
      date_to: "2026-03-31",
    });
  });

  it("drops unknown values, duplicates and malformed input", () => {
    const filters = parseAlertFilters({
      category: "NOT_COVERED,BOGUS,NOT_COVERED,",
      severity: "urgent",
      provider_id: "PRV-1,PRV-0003,'; drop",
      amount_min: "-10",
      amount_max: "abc",
      date_from: "2026-02-30",
      date_to: "31-01-2026",
    });
    expect(filters.category).toEqual(["NOT_COVERED"]);
    expect(filters.severity).toEqual([]);
    expect(filters.provider_id).toEqual(["PRV-0003"]);
    expect(filters.amount_min).toBe("");
    expect(filters.amount_max).toBe("");
    expect(filters.date_from).toBe("");
    expect(filters.date_to).toBe("");
  });

  it("returns empty filters for an empty URL", () => {
    expect(parseAlertFilters(new URLSearchParams())).toEqual(EMPTY_FILTERS);
  });
});

describe("round trip", () => {
  it("URL -> filters -> URL is stable", () => {
    const search = "?provider_id=PRV-0007&category=NOT_COVERED,NEAR_DUPLICATE&amount_min=1000&date_to=2026-10-31";
    const filters = parseAlertFilters(new URLSearchParams(search));
    expect(filtersToSearch(filters)).toBe(search);
  });

  it("filtersToSearch is empty without filters", () => {
    expect(filtersToSearch(EMPTY_FILTERS)).toBe("");
  });

  it("filtersToUrlPatch clears every key that is unset", () => {
    const patch = filtersToUrlPatch({ ...EMPTY_FILTERS, severity: ["critical", "high"] });
    expect(patch.severity).toBe("critical,high");
    expect(patch.category).toBe("");
    expect(Object.keys(patch)).toHaveLength(10);
  });
});

describe("filtersToApiQuery", () => {
  it("sends lists as arrays and leaves unset filters out", () => {
    const query = filtersToApiQuery({ ...EMPTY_FILTERS, category: ["NOT_COVERED"], amount_min: "500" });
    expect(query.category).toEqual(["NOT_COVERED"]);
    expect(query.amount_min).toBe("500");
    expect(query.severity).toBeUndefined();
    expect(query.date_from).toBeUndefined();
  });
});

describe("countActiveFilters and rangeProblems", () => {
  it("counts a range once", () => {
    expect(countActiveFilters({ ...EMPTY_FILTERS, amount_min: "1", amount_max: "2", category: ["NOT_COVERED"] })).toBe(
      2,
    );
    expect(countActiveFilters(EMPTY_FILTERS)).toBe(0);
  });

  it("flags inverted ranges", () => {
    expect(rangeProblems({ ...EMPTY_FILTERS, amount_min: "10000", amount_max: "2000" })).toEqual({
      amount: true,
      date: false,
    });
    expect(rangeProblems({ ...EMPTY_FILTERS, date_from: "2026-05-01", date_to: "2026-04-01" }).date).toBe(true);
    expect(rangeProblems({ ...EMPTY_FILTERS, amount_min: "2000", amount_max: "2000" }).amount).toBe(false);
  });
});

describe("parseAmount and parseIsoDate", () => {
  it.each([
    ["5000", "5000"],
    ["5,000", "5000"],
    ["₹1,00,000.5", "100000.5"],
    ["12.345", ""],
    ["", ""],
  ])("parseAmount(%s) -> %s", (input, expected) => {
    expect(parseAmount(input)).toBe(expected);
  });

  it("accepts real dates only", () => {
    expect(parseIsoDate("2024-02-29")).toBe("2024-02-29");
    expect(parseIsoDate("2026-02-29")).toBe("");
  });
});

describe("sorting", () => {
  it("falls back to the default sort", () => {
    expect(parseSort("bogus")).toBe("-amount");
    expect(parseSort("incident_date")).toBe("incident_date");
  });

  it("flips the current column and starts new columns in their natural direction", () => {
    expect(nextSort("-amount", "amount")).toBe("amount");
    expect(nextSort("amount", "amount")).toBe("-amount");
    expect(nextSort("-amount", "severity")).toBe("-severity");
    expect(nextSort("-amount", "claim_id")).toBe("claim_id");
    expect(nextSort("-amount", "incident_date")).toBe("-incident_date");
    expect(sortState("-incident_date")).toEqual({ field: "incident_date", desc: true });
  });
});

describe("model helpers", () => {
  it("describes rules and patterns", () => {
    expect(describePattern("C06 SUB_LIMIT_PER_DAY")).toEqual({ code: "C06", name: "Sub-limit per day" });
    expect(describePattern("NEAR_DUPLICATE")).toEqual({ code: null, name: "Near-duplicate" });
    expect(describePattern("SOMETHING_NEW")).toEqual({ code: null, name: "Something new" });
    expect(checkName("C12", "SETTLEMENT_CHECK")).toBe("Settlement check");
  });

  it("ranks severities from critical to review", () => {
    expect(severityRank("critical")).toBeLessThan(severityRank("low"));
    expect(severityRank("unknown")).toBe(5);
  });
});
