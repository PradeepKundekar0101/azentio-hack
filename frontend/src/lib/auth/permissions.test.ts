import { describe, expect, it } from "vitest";

import { canDecideEscalation, canManageUsers, canReviewAlert, ROLE_LABELS, ROLES } from "./permissions";

describe("permissions", () => {
  it("only admins manage users", () => {
    expect(canManageUsers("admin")).toBe(true);
    expect(canManageUsers("senior_reviewer")).toBe(false);
    expect(canManageUsers("analyst")).toBe(false);
    expect(canManageUsers(undefined)).toBe(false);
  });

  it("senior reviewers and admins decide escalations, but never their own", () => {
    expect(canDecideEscalation("senior_reviewer", "sunil", "asha")).toBe(true);
    expect(canDecideEscalation("admin", "root", "asha")).toBe(true);
    expect(canDecideEscalation("senior_reviewer", "sunil", "sunil")).toBe(false);
    expect(canDecideEscalation("analyst", "asha", "bala")).toBe(false);
    expect(canDecideEscalation(undefined, "asha", "bala")).toBe(false);
    expect(canDecideEscalation("admin", undefined, "asha")).toBe(false);
  });

  it("every signed-in role can review an alert", () => {
    for (const role of ROLES) expect(canReviewAlert(role)).toBe(true);
    expect(canReviewAlert(undefined)).toBe(false);
  });

  it("labels every role", () => {
    for (const role of ROLES) expect(ROLE_LABELS[role]).toBeTruthy();
  });
});
