/**
 * Display formatting: rupees in Indian digit grouping, counts, percentages and dates.
 *
 * Money arrives from the API as decimal strings ("142000.00"). It is never parsed into a
 * float for display: amounts are converted to integer paise with BigInt so that large
 * claims and portfolio totals format exactly. The rules match `inr()` in
 * backend/app/core/money.py, so amounts read the same in the UI and in explanations.
 */

export type Amount = string | number | null | undefined;

/** Shown for missing values in tables and cards. */
export const EMPTY = "–";

const RUPEE = "₹";
const MINUS = "−"; // U+2212, aligns with digits in tabular figures

const DECIMAL_RE = /^([+-])?(\d+)(?:\.(\d*))?$/;

/** Converts an amount to signed integer paise, rounding half away from zero. */
export function toPaise(value: Amount): bigint | null {
  if (value === null || value === undefined) return null;
  let text: string;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return null;
    text = value.toFixed(3);
  } else {
    text = value.trim().replace(/,/g, "");
  }
  const match = DECIMAL_RE.exec(text);
  if (!match) return null;
  const [, sign, whole, fraction = ""] = match;
  const digits = fraction.padEnd(3, "0");
  let paise = BigInt(whole) * BigInt(100) + BigInt(digits.slice(0, 2));
  if (Number(digits[2]) >= 5) paise += BigInt(1);
  return sign === "-" ? -paise : paise;
}

/** Groups an unsigned integer string the Indian way: 12,34,56,789. */
export function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

export interface FormatINROptions {
  /** Always show two paise digits. By default paise appear only when non-zero. */
  paise?: boolean;
  /** Prefix positive amounts with "+". */
  signed?: boolean;
}

/**
 * Formats rupees with Indian digit grouping. Paise appear only when non-zero unless
 * `paise: true` asks for them, so no amount is ever rounded away.
 *
 * formatINR("142000.00", { paise: true }) -> "₹1,42,000.00"
 * formatINR("6000.00") -> "₹6,000"
 * formatINR("1250.5") -> "₹1,250.50"
 */
export function formatINR(value: Amount, options: FormatINROptions = {}): string {
  const paise = toPaise(value);
  if (paise === null) return EMPTY;
  const negative = paise < BigInt(0);
  const abs = negative ? -paise : paise;
  const rupees = abs / BigInt(100);
  const rem = abs % BigInt(100);
  let out = RUPEE + groupIndian(rupees.toString());
  if (options.paise || rem !== BigInt(0)) {
    out += "." + rem.toString().padStart(2, "0");
  }
  if (negative) return MINUS + out;
  if (options.signed && abs !== BigInt(0)) return "+" + out;
  return out;
}

const LAKH = 100000;
const CRORE = 10000000;

function trimDecimal(value: number, digits: number): string {
  return value.toFixed(digits).replace(/\.0+$/, "");
}

/**
 * Compact rupee amounts for KPI cards and chart axes.
 *
 * Below one lakh the full rupee amount is shown (no paise). From one lakh it switches to
 * lakhs ("₹1.4 L") and from one crore to crores ("₹2.3 Cr").
 */
export function formatINRCompact(value: Amount, digits = 1): string {
  const paise = toPaise(value);
  if (paise === null) return EMPTY;
  const negative = paise < BigInt(0);
  const abs = Number(negative ? -paise : paise) / 100;
  let body: string;

  const lakhs = Number((abs / LAKH).toFixed(digits));
  const crores = Number((abs / CRORE).toFixed(digits));
  if (abs < LAKH && Math.round(abs) < LAKH) {
    body = RUPEE + groupIndian(Math.round(abs).toString());
  } else if (lakhs < 100) {
    body = `${RUPEE}${trimDecimal(lakhs, digits)} L`;
  } else if (crores < 100) {
    body = `${RUPEE}${trimDecimal(crores, digits)} Cr`;
  } else {
    body = `${RUPEE}${groupIndian(Math.round(abs / CRORE).toString())} Cr`;
  }
  return negative ? MINUS + body : body;
}

const nf = new Intl.NumberFormat("en-IN");

/** Counts with Indian grouping: 12,34,567. */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY;
  return nf.format(value);
}

/**
 * Formats a ratio (0.234) as a percentage ("23.4%").
 * Pass `{ ratio: false }` when the API already sends percentage points (23.4).
 */
export function formatPercent(
  value: number | string | null | undefined,
  { digits = 1, ratio = true }: { digits?: number; ratio?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return EMPTY;
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return EMPTY;
  const pct = ratio ? n * 100 : n;
  return `${pct.toFixed(digits)}%`;
}

const TZ = "Asia/Kolkata";
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

const dateFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: TZ,
});
const dateOnlyFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: TZ,
});

function toDate(value: string | Date): Date | null {
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "12 Mar 2026". Date-only strings ("2026-03-12") are never shifted by time zone. */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return EMPTY;
  if (typeof value === "string" && DATE_ONLY_RE.test(value)) {
    const d = toDate(`${value}T00:00:00Z`);
    return d ? dateOnlyFmt.format(d) : EMPTY;
  }
  const d = toDate(value);
  return d ? dateFmt.format(d) : EMPTY;
}

/** "12 Mar 2026, 14:05" in India Standard Time. */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return EMPTY;
  const d = toDate(value);
  return d ? dateTimeFmt.format(d) : EMPTY;
}
