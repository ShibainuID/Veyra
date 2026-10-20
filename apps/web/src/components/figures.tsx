import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { formatAbsolute, formatMoney, formatMoneyRange, formatRange, formatRelative } from "../lib/format";
import { useNow } from "../lib/use-now";

/** Figures, IDs, and codes: Atkinson Hyperlegible Mono with tabular numerals. */
export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("figures", className)}>{children}</span>;
}

type MoneyProps = {
  currency?: string;
  className?: string;
} & (
  | { minor: number; signed?: boolean; whole?: boolean; low?: never; high?: never; exact?: never }
  | { low: number; high: number; exact?: boolean; minor?: never; signed?: never; whole?: never }
);

/** Minor units to "2,496.00 USD"; a low/high pair to "2,496–2,912 USD". */
export function Money(props: MoneyProps) {
  const currency = props.currency ?? "USD";
  const text =
    props.minor !== undefined
      ? formatMoney(props.minor, currency, { signed: props.signed, whole: props.whole })
      : formatMoneyRange(props.low, props.high, currency, { exact: props.exact });
  // In a narrow column the line may break before the currency code, never inside the figure.
  const split = text.lastIndexOf(" ");
  return (
    <span className={cn("figures", props.className)}>
      <span className="whitespace-nowrap">{text.slice(0, split)}</span> {text.slice(split + 1)}
    </span>
  );
}

/** "480–560 kg". */
export function Range({ low, high, unit, className }: { low: number; high: number; unit?: string; className?: string }) {
  return <span className={cn("figures whitespace-nowrap", className)}>{formatRange(low, high, unit)}</span>;
}

export interface TimestampProps {
  /** ISO 8601 instant. */
  value: string;
  /** "both" prints "20 Oct 2026, 09:42 · 2 min ago". */
  mode?: "both" | "absolute" | "relative";
  timeZone?: string;
  className?: string;
}

export function Timestamp({ value, mode = "both", timeZone, className }: TimestampProps) {
  const now = useNow(30_000, mode !== "absolute");
  const absolute = formatAbsolute(value, timeZone);
  const relative = formatRelative(value, now);
  return (
    <time dateTime={value} title={mode === "relative" ? absolute : undefined} className={cn("figures whitespace-nowrap", className)}>
      {mode !== "relative" && absolute}
      {mode === "both" && <span className="text-muted"> · {relative}</span>}
      {mode === "relative" && relative}
    </time>
  );
}
