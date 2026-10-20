/** Indicative valuation arithmetic, matching the server: value = floor(weight_kg × unit price per kg), per end. */

/** "5.20" → 520 minor units; null when the text isn't a positive price with at most two decimals. */
export function parsePriceMinor(text: string, exponent = 2): number | null {
  const match = /^\s*(\d+)(?:[.,](\d+))?\s*$/.exec(text);
  if (!match) return null;
  const fraction = match[2] ?? "";
  if (fraction.length > exponent) return null;
  const minor = Number(match[1]) * 10 ** exponent + Number(fraction.padEnd(exponent, "0") || 0);
  return minor > 0 ? minor : null;
}

/** "512.5" → 512.5; null when not a positive number. */
export function parseKg(text: string): number | null {
  const value = Number(text.replace(",", ".").trim());
  return text.trim() !== "" && Number.isFinite(value) && value > 0 ? value : null;
}

export function valueMinor(weightKg: number, unitPriceMinorPerKg: number): number {
  // Work in thousandths of a kilogram so 512.5 × 520 never meets float drift before the floor.
  return Math.floor((Math.round(weightKg * 1000) * unitPriceMinorPerKg) / 1000);
}

export function valueRange(lowKg: number, highKg: number, unitPriceMinorPerKg: number): { low: number; high: number } {
  return { low: valueMinor(lowKg, unitPriceMinorPerKg), high: valueMinor(highKg, unitPriceMinorPerKg) };
}
