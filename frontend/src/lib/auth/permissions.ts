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

/** Higher rank decides more. Matches ROLE_RANK in the backend. */
export const ROLE_RANK: Record<Role, number> = { analyst: 0, senior_reviewer: 1, admin: 2 };

const rankOf = (role: string | null | undefined) => (ROLE_RANK as Record<string, number>)[role ?? ""] ?? 1;

/** Escalation goes only upwards: an analyst to a senior reviewer or an admin, a senior reviewer to an admin. */
export function escalationTargetsFor(role: Role | undefined): Role[] {
  if (!role) return [];
  return ROLES.filter((target) => target !== "analyst" && ROLE_RANK[target] > ROLE_RANK[role]);
}

/** The level it was escalated to, or higher, decides it; never whoever escalated it. */
export function canDecideEscalation(
  role: Role | undefined,
  username: string | undefined,
  escalatedBy: string | null,
  escalatedTo: string | null = "senior_reviewer",
) {
  if (!role || !username) return false;
  return ROLE_RANK[role] >= rankOf(escalatedTo) && escalatedBy !== username;
}

/** Roles that see the review queue: anyone an alert can be escalated to. */
export const hasReviewQueue = (role: Role | undefined) => role !== undefined;

/** Any signed-in role may review, dismiss, request evidence or escalate an alert that is not escalated. */
export const canReviewAlert = (role: Role | undefined) => role !== undefined;
