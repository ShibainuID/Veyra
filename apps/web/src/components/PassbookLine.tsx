import { Ban } from "lucide-react";
import type { ReactNode } from "react";
import { formatClock, formatCountdown, formatDayMonth, formatMoney, lineNumber } from "../lib/format";
import { useNow } from "../lib/use-now";
import { Provenance, type Source } from "./Provenance";
import { Stamp, type StampProps } from "./Stamp";
import { StatusPill } from "./StatusPill";

export type PassbookStatus = "posted" | "awaiting" | "void";

export interface PassbookAmount {
  /** Signed minor units: negative leaves the sandbox wallet, positive arrives. */
  minor: number;
  currency?: string;
  /** Names a non-wallet figure ("Insured", "Valued"). */
  label?: string;
  /** Print "+" / "−". Defaults to true for wallet movements (no label). */
  signed?: boolean;
}

export interface PassbookLineData {
  id: string;
  /** Position in this animal's passbook, printed as three digits. */
  number: number;
  /** When the line was written (ISO 8601). */
  at: string;
  title: string;
  detail?: ReactNode;
  amount?: PassbookAmount;
  /** Running wallet balance after this line, in minor units. */
  balanceMinor?: number;
  status: PassbookStatus;
  stamp?: Omit<StampProps, "className">;
  /** Awaiting lines: when the approval window closes (ISO 8601). */
  expiresAt?: string;
  source?: Source;
}

export interface PassbookLineProps extends PassbookLineData {
  timeZone?: string;
}

function AwaitingSlot({ expiresAt }: { expiresAt?: string }) {
  const now = useNow(1000, Boolean(expiresAt));
  if (!expiresAt) return <span className="pb-slot">Awaiting stamp</span>;
  const remaining = new Date(expiresAt).getTime() - now;
  if (remaining <= 0) {
    return (
      <span className="pb-slot" data-expired="">
        Expired · <time dateTime={expiresAt}>prepare again</time>
      </span>
    );
  }
  return (
    <span className="pb-slot">
      Awaiting stamp · expires <time dateTime={expiresAt}>{formatCountdown(remaining)}</time>
    </span>
  );
}

/** One numbered, dated passbook line. Render inside an `<ol className="pb-list">`. */
export function PassbookLine({
  number,
  at,
  title,
  detail,
  amount,
  balanceMinor,
  status,
  stamp,
  expiresAt,
  source,
  timeZone,
}: PassbookLineProps) {
  const currency = amount?.currency ?? "USD";
  const signed = amount?.signed ?? amount?.label === undefined;
  const hasFoot = Boolean(source || status === "awaiting" || status === "void" || stamp);
  return (
    <li className="pb-line" data-status={status}>
      <div className="pb-gutter">
        <span className="pb-number">
          <span className="sr-only">Line </span>
          {lineNumber(number)}
        </span>
        <time dateTime={at} className="flex flex-col">
          <span>{formatDayMonth(at, timeZone)}</span>
          <span>{formatClock(at, timeZone)}</span>
        </time>
      </div>
      <div className="min-w-0">
        <p className="pb-title font-bold">{title}</p>
        {detail && <div className="mt-0.5 text-sm text-muted">{detail}</div>}
      </div>
      <div className="pb-amount">
        {amount && (
          <>
            {amount.label && <span className="block font-sans text-sm text-muted">{amount.label}</span>}
            <span className="pb-amount-value block font-bold">{formatMoney(amount.minor, currency, { signed })}</span>
          </>
        )}
        {balanceMinor !== undefined && (
          <span className="mt-0.5 block text-sm text-muted">
            <span className="font-sans">Balance </span>
            {formatMoney(balanceMinor, currency, { bare: true })}
          </span>
        )}
      </div>
      {hasFoot && (
        <div className="pb-foot">
          {source && <Provenance source={source} />}
          {status === "void" && <StatusPill tone="neutral" icon={Ban} label="Void" />}
          {status === "awaiting" && <AwaitingSlot expiresAt={expiresAt} />}
          {status !== "awaiting" && stamp && <Stamp {...stamp} timeZone={stamp.timeZone ?? timeZone} />}
        </div>
      )}
    </li>
  );
}
