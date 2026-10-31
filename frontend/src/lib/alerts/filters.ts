/**
 * Alert filters as they live in the URL, and their mapping to the API query.
 *
 * The URL keeps one parameter per filter with list values joined by commas
 * (`?category=NOT_COVERED,EXCLUDED_SERVICE&amount_min=5000`), so a view can be shared and
 * the same string opens the alerts list or the dashboard with identical filters. The API
 * takes the same names with repeated parameters, which openapi-fetch produces from arrays.
 * Anything malformed in the URL is ignored rather than sent on.
 */
import {
  ALERT_STATUSES,
  type AlertCategory,
  type AlertStatus,
  AMOUNT_TYPES,
  type AmountType,
  CATEGORIES,
  CLAIM_TYPES,
  type ClaimType,
  type Severity,
  SEVERITIES,
} from "./model";

export interface AlertFilters {
  claim_type: ClaimType[];
  provider_id: string[];
  category: AlertCategory[];
  severity: Severity[];
  amount_type: AmountType[];
  status: AlertStatus[];
  /** Whole or decimal rupees as typed, e.g. "5000" or "2500.50". */
  amount_min: string;
  amount_max: string;
  /** Incident date range, ISO "YYYY-MM-DD", inclusive. */
  date_from: string;
  date_to: string;
}

export type ListFilterKey = "claim_type" | "provider_id" | "category" | "severity" | "amount_type" | "status";
export type FilterKey = keyof AlertFilters;

export const LIST_FILTER_KEYS = [
  "claim_type",
  "provider_id",
  "category",
  "severity",
  "amount_type",
  "status",
] as const satisfies readonly ListFilterKey[];

export const FILTER_KEYS = [
  ...LIST_FILTER_KEYS,
  "amount_min",
  "amount_max",
  "date_from",
  "date_to",
] as const satisfies readonly FilterKey[];

/** Defaults for `useUrlState`: every filter empty. */
export const FILTER_URL_DEFAULTS: Record<FilterKey, string> = {
  claim_type: "",
  provider_id: "",
  category: "",
  severity: "",
  amount_type: "",
  status: "",
  amount_min: "",
  amount_max: "",
  date_from: "",
  date_to: "",
};

export const EMPTY_FILTERS: AlertFilters = {
  claim_type: [],
  provider_id: [],
  category: [],
  severity: [],
  amount_type: [],
  status: [],
  amount_min: "",
  amount_max: "",
  date_from: "",
  date_to: "",
};

const PROVIDER_RE = /^PRV-\d{4}$/;
const AMOUNT_RE = /^\d{1,10}(\.\d{1,2})?$/;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** A non-negative rupee amount with at most two decimals; commas and spaces are ignored. */
export function parseAmount(value: string | null | undefined): string {
  const text = (value ?? "").replace(/[,\s₹]/g, "");
  return AMOUNT_RE.test(text) ? text : "";
}

/** A real calendar date in ISO form, or "". */
export function parseIsoDate(value: string | null | undefined): string {
  const match = DATE_RE.exec(value ?? "");
  if (!match) return "";
  const [, y, m, d] = match.map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const valid = date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
  return valid ? (value as string) : "";
}

function parseList<T extends string>(value: string | null | undefined, allowed: (v: string) => v is T): T[] {
  if (!value) return [];
  const out: T[] = [];
  for (const part of value.split(",")) {
    const v = part.trim();
    if (v && allowed(v) && !out.includes(v)) out.push(v);
  }
  return out;
}

const oneOf =
  <T extends string>(values: readonly T[]) =>
  (v: string): v is T =>
    (values as readonly string[]).includes(v);

const isProvider = (v: string): v is string => PROVIDER_RE.test(v);

type ParamSource = { get(name: string): string | null } | Partial<Record<string, string>>;

function getter(source: ParamSource): (name: string) => string | null {
  if (typeof (source as URLSearchParams).get === "function") {
    return (name) => (source as URLSearchParams).get(name);
  }
  return (name) => (source as Partial<Record<string, string>>)[name] ?? null;
}

/** Reads filters from URL search params (or a `useUrlState` record), dropping anything invalid. */
export function parseAlertFilters(source: ParamSource): AlertFilters {
  const get = getter(source);
  return {
    claim_type: parseList(get("claim_type"), oneOf(CLAIM_TYPES)),
    provider_id: parseList(get("provider_id"), isProvider),
    category: parseList(get("category"), oneOf(CATEGORIES)),
    severity: parseList(get("severity"), oneOf(SEVERITIES)),
    amount_type: parseList(get("amount_type"), oneOf(AMOUNT_TYPES)),
    status: parseList(get("status"), oneOf(ALERT_STATUSES)),
    amount_min: parseAmount(get("amount_min")),
    amount_max: parseAmount(get("amount_max")),
    date_from: parseIsoDate(get("date_from")),
    date_to: parseIsoDate(get("date_to")),
  };
}

/** The URL form of each filter: lists joined with commas, "" when unset. */
export function filtersToUrlPatch(filters: AlertFilters): Record<FilterKey, string> {
  return {
    claim_type: filters.claim_type.join(","),
    provider_id: filters.provider_id.join(","),
    category: filters.category.join(","),
    severity: filters.severity.join(","),
    amount_type: filters.amount_type.join(","),
    status: filters.status.join(","),
    amount_min: filters.amount_min,
    amount_max: filters.amount_max,
    date_from: filters.date_from,
    date_to: filters.date_to,
  };
}

/** "?category=NOT_COVERED&amount_min=5000", or "" with no filters. Used to link between pages. */
export function filtersToSearch(filters: AlertFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filtersToUrlPatch(filters))) {
    if (value) params.set(key, value);
  }
  const qs = params.toString().replace(/%2C/g, ",");
  return qs ? `?${qs}` : "";
}

/** The query for GET /alerts and /dashboard/summary. Unset filters are left out. */
export function filtersToApiQuery(filters: AlertFilters) {
  const list = <T>(values: T[]) => (values.length ? values : undefined);
  return {
    claim_type: list(filters.claim_type),
    provider_id: list(filters.provider_id),
    category: list(filters.category),
    severity: list(filters.severity),
    amount_type: list(filters.amount_type),
    status: list(filters.status),
    amount_min: filters.amount_min || undefined,
    amount_max: filters.amount_max || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
  };
}

/** Number of filters in use; a range counts once. */
export function countActiveFilters(filters: AlertFilters): number {
  let n = LIST_FILTER_KEYS.filter((key) => filters[key].length > 0).length;
  if (filters.amount_min || filters.amount_max) n += 1;
  if (filters.date_from || filters.date_to) n += 1;
  return n;
}

/** True when the minimum is above the maximum (amounts or dates); the API would return nothing. */
export function rangeProblems(filters: AlertFilters): { amount: boolean; date: boolean } {
  const amount =
    Boolean(filters.amount_min && filters.amount_max) && Number(filters.amount_min) > Number(filters.amount_max);
  const date = Boolean(filters.date_from && filters.date_to) && filters.date_from > filters.date_to;
  return { amount, date };
}

export const ALERT_SORTS = [
  "-amount",
  "amount",
  "-severity",
  "severity",
  "-incident_date",
  "incident_date",
  "category",
  "-category",
  "claim_id",
  "-claim_id",
  "status",
  "-status",
  "id",
  "-id",
] as const;
export type AlertSort = (typeof ALERT_SORTS)[number];
export const DEFAULT_SORT: AlertSort = "-amount";

export type SortField = "amount" | "severity" | "incident_date" | "category" | "claim_id" | "status" | "id";

export function parseSort(value: string | null | undefined): AlertSort {
  return (ALERT_SORTS as readonly string[]).includes(value ?? "") ? (value as AlertSort) : DEFAULT_SORT;
}

/** The field and direction of a sort value. */
export function sortState(sort: AlertSort): { field: SortField; desc: boolean } {
  const desc = sort.startsWith("-");
  return { field: (desc ? sort.slice(1) : sort) as SortField, desc };
}

/**
 * The sort after clicking a column header: the same column flips direction; a new column
 * starts with its natural direction (largest amounts, most severe and latest dates first).
 * The API treats "-severity" as most severe first.
 */
export function nextSort(current: AlertSort, field: SortField): AlertSort {
  const { field: currentField, desc } = sortState(current);
  if (currentField === field) return parseSort(desc ? field : `-${field}`);
  const startsDesc = field === "amount" || field === "incident_date" || field === "severity";
  return parseSort(startsDesc ? `-${field}` : field);
}
