import { describe, expect, it } from "vitest";

import { parseClaimSort, parseReview, parseStatus, reviewLabel } from "./review";

describe("claims list URL parsing", () => {
  it("defaults to open claims, every result, newest incident first", () => {
    expect(parseStatus("")).toBe("open");
    expect(parseStatus("bogus")).toBe("open");
    expect(parseReview("")).toBe("all");
    expect(parseClaimSort("drop table")).toBe("-incident_date");
  });

  it("keeps valid values", () => {
    expect(parseStatus("settled")).toBe("settled");
    expect(parseReview("clean")).toBe("clean");
    expect(parseClaimSort("-leakage")).toBe("-leakage");
  });

  it("labels review states for people", () => {
    expect(reviewLabel("clean")).toBe("Clean, ready to pay");
    expect(reviewLabel("not_validated")).toBe("Not validated");
  });

  it("does not call a claim with nothing payable ready to pay", () => {
    expect(reviewLabel("clean", "0.00")).toBe("Clean, nothing payable");
    expect(reviewLabel("clean", "2961.00")).toBe("Clean, ready to pay");
    expect(reviewLabel("flagged", "0.00")).toBe("Flagged");
  });
});
