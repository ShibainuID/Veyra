const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A calendar date ("2026-10-01") as "01 Oct 2026", with no time-zone shift. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day} ${MONTHS[Number(month) - 1] ?? month} ${year}`;
}

/** A fresh key for one provider call that is safe to repeat. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
