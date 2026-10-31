import { describe, expect, it } from "vitest";

import { HOME_PATH, loginPath, safeNextPath } from "./redirect";

describe("safeNextPath", () => {
  it.each([
    ["/alerts", "/alerts"],
    ["/alerts?severity=high&page=2", "/alerts?severity=high&page=2"],
    ["/imports#issues", "/imports#issues"],
    ["/", "/"],
  ])("keeps the same-site path %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });

  it.each([
    [null],
    [undefined],
    [""],
    ["alerts"],
    ["https://evil.example/alerts"],
    ["javascript:alert(1)"],
    ["//evil.example"],
    ["/\\evil.example"],
    ["/\t/evil.example"],
    ["/\n/evil.example"],
    ["/login"],
    ["/login?next=/alerts"],
  ])("falls back to home for %j", (input) => {
    expect(safeNextPath(input)).toBe(HOME_PATH);
  });
});

describe("loginPath", () => {
  it("adds the return path", () => {
    expect(loginPath("/alerts?page=2")).toBe("/login?next=%2Falerts%3Fpage%3D2");
  });

  it("omits next for home and for unsafe targets", () => {
    expect(loginPath("/")).toBe("/login");
    expect(loginPath("//evil.example")).toBe("/login");
    expect(loginPath()).toBe("/login");
  });
});
