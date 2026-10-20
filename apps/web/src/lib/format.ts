/**
 * Formatting for figures, IDs, and times. Money is always integer minor units plus an ISO
 * currency code (never floats); every figure is shown with its unit.
 */

const MINUS = "−";
const EN_DASH = "–";

const CURRENCY_EXPONENT: Record<string, number> = { USD: 2, EUR: 2, IDR: 2, JPY: 0 };

const grouped = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0, useGrouping: true });

export function currencyExponent(currency: string): number {
  return CURRENCY_EXPONENT[currency.toUpperCase()] ?? 2;
}

function splitMinor(absMinor: number, exponent: number): { major: number; fraction: string } {
  const factor = 10 ** exponent;
  const major = Math.floor(absMinor / factor);
  const fraction = exponent > 0 ? String(absMinor % factor).padStart(exponent, "0") : "";
  return { major, fraction };
}

function assertMinor(minor: number): void {
  if (!Number.isInteger(minor)) {
    throw new TypeError(`money must be integer minor units, got ${minor}`);
  }
}

export interface MoneyFormatOptions {
  /** Prefix positives with "+" and negatives with a true minus sign. */
  signed?: boolean;
  /** Drop the fraction, rounding to the nearest whole unit. */
  whole?: boolean;
  /** Omit the currency code (for columns that state it in the header). */
  bare?: boolean;
}

/** 249600 USD → "2,496.00 USD"; -8736 → "−87.36 USD"; signed 8736 → "+87.36 USD". */
export function formatMoney(minor: number, currency = "USD", options: MoneyFormatOptions = {}): string {
  assertMinor(minor);
  const exponent = currencyExponent(currency);
  const abs = Math.abs(minor);
  let body: string;
  if (options.whole) {
    body = grouped.format(Math.round(abs / 10 ** exponent));
  } else {
    const { major, fraction } = splitMinor(abs, exponent);
    body = fraction ? `${grouped.format(major)}.${fraction}` : grouped.format(major);
  }
  let sign = "";
  if (minor < 0) sign = MINUS;
  else if (options.signed && minor > 0) sign = "+";
  const code = options.bare ? "" : ` ${currency.toUpperCase()}`;
  return `${sign}${body}${code}`;
}

export interface RangeFormatOptions {
  /** Show the fraction ("2,496.00–2,912.00 USD"). Default is whole units. */
  exact?: boolean;
}

/**
 * An indicative range: "2,496–2,912 USD". Whole-unit ranges round outward (low down, high up)
 * so the printed range never claims more certainty than the estimate has.
 */
export function formatMoneyRange(
  lowMinor: number,
  highMinor: number,
  currency = "USD",
  options: RangeFormatOptions = {},
): string {
  assertMinor(lowMinor);
  assertMinor(highMinor);
  const [low, high] = lowMinor <= highMinor ? [lowMinor, highMinor] : [highMinor, lowMinor];
  const code = currency.toUpperCase();
  if (options.exact) {
    return `${formatMoney(low, code, { bare: true })}${EN_DASH}${formatMoney(high, code, { bare: true })} ${code}`;
  }
  const factor = 10 ** currencyExponent(code);
  const lowWhole = Math.floor(low / factor);
  const highWhole = Math.ceil(high / factor);
  const fmt = (n: number) => (n < 0 ? `${MINUS}${grouped.format(-n)}` : grouped.format(n));
  return `${fmt(lowWhole)}${EN_DASH}${fmt(highWhole)} ${code}`;
}

/** "480–560 kg"; equal ends collapse to "480 kg". */
export function formatRange(low: number, high: number, unit?: string): string {
  const fmt = (n: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n);
  const body = low === high ? fmt(low) : `${fmt(Math.min(low, high))}${EN_DASH}${fmt(Math.max(low, high))}`;
  return unit ? `${body} ${unit}` : body;
}

/**
 * The number printed on an animal's ear tag: the last three digits of its ID
 * ("animal-demo-001" → "001", "animal-demo-12" → "012"). IDs without digits fall back to their
 * last three letters in capitals.
 */
export function tagNumber(animalId: string): string {
  const digits = /(\d+)\D*$/.exec(animalId)?.[1];
  if (digits) return digits.slice(-3).padStart(3, "0");
  const letters = animalId.replace(/[^a-z0-9]/gi, "");
  return letters.slice(-3).toUpperCase() || "---";
}

/** Three-digit passbook line number: 4 → "004". */
export function lineNumber(n: number): string {
  return String(Math.max(0, Math.trunc(n))).padStart(3, "0");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface DateParts {
  year: number;
  month: number;
  day: number;
  hour: string;
  minute: string;
}

function toDate(value: string | number | Date): Date {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) throw new RangeError(`invalid date: ${String(value)}`);
  return date;
}

function dateParts(value: string | number | Date, timeZone?: string): DateParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(toDate(value));
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "0";
  return {
    year: Number(get("year")),
    month: Number(get("month")),
    day: Number(get("day")),
    hour: get("hour").padStart(2, "0"),
    minute: get("minute").padStart(2, "0"),
  };
}

/** "20 Oct 2026, 09:42" */
export function formatAbsolute(value: string | number | Date, timeZone?: string): string {
  const p = dateParts(value, timeZone);
  return `${p.day} ${MONTHS[p.month - 1]} ${p.year}, ${p.hour}:${p.minute}`;
}

/** "20 Oct" and "08:31", for the passbook's date gutter. */
export function formatDayMonth(value: string | number | Date, timeZone?: string): string {
  const p = dateParts(value, timeZone);
  return `${p.day} ${MONTHS[p.month - 1]}`;
}

export function formatClock(value: string | number | Date, timeZone?: string): string {
  const p = dateParts(value, timeZone);
  return `${p.hour}:${p.minute}`;
}

/** Stamp date: "20 OCT 08:31". */
export function formatStampTime(value: string | number | Date, timeZone?: string): string {
  const p = dateParts(value, timeZone);
  return `${p.day} ${MONTHS[p.month - 1]!.toUpperCase()} ${p.hour}:${p.minute}`;
}

/** "just now", "2 min ago", "3 h ago", "yesterday", "4 days ago", "in 5 min". */
export function formatRelative(value: string | number | Date, now: number = Date.now()): string {
  const diffMs = toDate(value).getTime() - now;
  const future = diffMs > 0;
  const abs = Math.abs(diffMs);
  const s = Math.round(abs / 1000);
  if (s < 45) return future ? "in a moment" : "just now";
  const m = Math.round(s / 60);
  if (m < 60) return future ? `in ${m} min` : `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return future ? `in ${h} h` : `${h} h ago`;
  const d = Math.round(h / 24);
  if (d === 1) return future ? "tomorrow" : "yesterday";
  return future ? `in ${d} days` : `${d} days ago`;
}

/** Remaining time as "mm:ss" (or "h:mm:ss" past an hour); never negative. */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Initials for a stamp signature: "Wahyu Santoso" → "W.S." */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => `${part[0]!.toUpperCase()}.`)
    .join("");
}
