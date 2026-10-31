/**
 * What each role may do in the interface. The backend enforces the same rules; this only decides
 * which controls to show, so nobody is offered an action that would be refused.
 */

import type { Schemas } from "@/lib/api/client";

export type Role = Schemas["Role"];

export const ROLES = ["analyst", "senior_reviewer", "admin"] as const satisfies readonly Role[];

export const ROLE_LABELS: Record<Role, string> = {
  analyst: "Claims analyst",
  senior_reviewer: "Senior claims reviewer",
  admin: "Administrator",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  analyst: "Reviews alerts, requests evidence and escalates findings.",
  senior_reviewer: "Everything an analyst does, and decides escalated alerts.",
  admin: "Everything a senior reviewer does, and onboards users.",
};

export const roleLabel = (role: string) => (ROLE_LABELS as Record<string, string>)[role] ?? role;

/** Admins onboard and manage users. */
export const canManageUsers = (role: Role | undefined) => role === "admin";

/** Escalated alerts are decided by a senior reviewer or an admin, never by whoever escalated them. */
export function canDecideEscalation(role: Role | undefined, username: string | undefined, escalatedBy: string | null) {
  if (!role || !username) return false;
  if (role !== "senior_reviewer" && role !== "admin") return false;
  return escalatedBy !== username;
}

/** Any signed-in role may review, dismiss, request evidence or escalate an alert that is not escalated. */
export const canReviewAlert = (role: Role | undefined) => role !== undefined;
