/**
 * Typed amounts to integer minor units, without floating point: "1,200.50" USD → 120050.
 * Returns null for anything that isn't a plain non-negative amount with at most the currency's
 * decimal places.
 */
import { currencyExponent } from "./format";

export function parseMoneyInput(text: string, currency = "USD"): number | null {
  const exponent = currencyExponent(currency);
  const cleaned = text.trim().replace(/\s+/g, "").replace(new RegExp(`${currency}$`, "i"), "");
  if (!cleaned) return null;
  // Grouping commas are allowed only in proper thousands positions.
  const pattern = exponent > 0 ? /^(\d{1,3}(,\d{3})*|\d+)?(\.\d*)?$/ : /^(\d{1,3}(,\d{3})*|\d+)$/;
  if (!pattern.test(cleaned) || cleaned === ".") return null;
  const [wholePart = "", fractionPart = ""] = cleaned.replace(/,/g, "").split(".");
  if (fractionPart.length > exponent) return null;
  const whole = wholePart === "" ? 0 : Number(wholePart);
  const fraction = Number(fractionPart.padEnd(exponent, "0") || "0");
  const minor = whole * 10 ** exponent + fraction;
  return Number.isSafeInteger(minor) ? minor : null;
}
