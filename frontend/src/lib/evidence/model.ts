import type { Schemas } from "@/lib/api/client";
import { EMPTY, formatINR } from "@/lib/format";

export type Investigation = Schemas["InvestigationOut"];
export type InvestigationRow = Schemas["InvestigationRow"];
export type EvidenceEvent = Schemas["EvidenceEventOut"];
export type EvidenceFinding = Schemas["EvidenceFinding"];
export type Recommendation = Schemas["RecommendationOut"];
export type EvidenceKind = EvidenceEvent["kind"];

export const KIND_LABELS: Record<EvidenceKind, string> = {
  opened: "Investigation opened",
  recalculated: "Recalculated",
  decision: "Decision",
  override: "Override",
  note: "Note",
  exported: "Report downloaded",
};

/** Timeline filters. "System" is everything recorded without an analyst's input. */
export type EvidenceFilter = "all" | "decision" | "override" | "note" | "system";

export const EVIDENCE_FILTERS: readonly { value: EvidenceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "decision", label: "Decisions" },
  { value: "override", label: "Overrides" },
  { value: "note", label: "Notes" },
  { value: "system", label: "System" },
];

export function matchesFilter(event: Pick<EvidenceEvent, "kind">, filter: EvidenceFilter): boolean {
  if (filter === "all") return true;
  if (filter === "system") return event.kind === "opened" || event.kind === "recalculated" || event.kind === "exported";
  return event.kind === filter;
}

/** Decision statuses, including the ones review and escalation add. Unknown values read as words. */
const DECISION_LABELS: Record<string, string> = {
  open: "Reopened",
  reviewed: "Confirmed discrepancy",
  dismissed: "False positive",
  evidence_requested: "Evidence requested",
  escalated: "Escalated",
};

export function decisionLabel(status: string | null | undefined): string {
  if (!status) return "Not decided";
  return DECISION_LABELS[status] ?? status.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

export type Tone = "good" | "bad" | "warn" | "neutral";

export function decisionTone(status: string | null | undefined): Tone {
  if (status === "reviewed") return "good";
  if (status === "dismissed") return "neutral";
  if (status === "escalated" || status === "evidence_requested") return "warn";
  return "neutral";
}

/** "a1b2c3d4…9f0e" for showing a SHA-256 without taking a whole line. */
export function shortHash(hash: string | null | undefined, head = 8, tail = 4): string {
  if (!hash) return EMPTY;
  if (hash.length <= head + tail + 1) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

/** Signed rupee difference ("−₹1,500", "+₹200", "₹0"), from decimal strings without float error. */
export function formatDelta(from: string | null | undefined, to: string | null | undefined): string {
  if (from == null || to == null) return EMPTY;
  const paise = (value: string) => Math.round(Number(value) * 100);
  const diff = paise(to) - paise(from);
  if (diff === 0) return formatINR("0");
  const amount = formatINR((Math.abs(diff) / 100).toFixed(2));
  return diff < 0 ? `−${amount}` : `+${amount}`;
}

const RELATIVE = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });
const STEPS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.35],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** "2 minutes ago", "yesterday". `now` is injectable for tests. */
export function relativeTime(value: string | Date | null | undefined, now: Date = new Date()): string {
  if (!value) return EMPTY;
  const at = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(at.getTime())) return EMPTY;
  let delta = (at.getTime() - now.getTime()) / 1000;
  if (Math.abs(delta) < 45) return "just now";
  for (const [unit, size] of STEPS) {
    if (Math.abs(delta) < size) return RELATIVE.format(Math.round(delta), unit);
    delta /= size;
  }
  return EMPTY;
}

/** The figure an analyst applies: the override if there is one, otherwise the system's correction. */
export function appliedCorrection(finding: EvidenceFinding): string | null {
  return finding.effective_correction ?? null;
}

export function isOverridden(finding: EvidenceFinding): boolean {
  return finding.override !== null && finding.override !== undefined && !finding.override.reverted;
}

export function reportUrl(claimId: string, format: "pdf" | "json"): string {
  return `/api/v1/evidence/claims/${encodeURIComponent(claimId)}/report?format=${format}`;
}
