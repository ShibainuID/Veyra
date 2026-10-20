import { cn } from "../lib/cn";
import { formatStampTime } from "../lib/format";

export type StampKind = "approved" | "posted" | "declined" | "failed" | "unknown" | "confirmed";

const WORD: Record<StampKind, string> = {
  approved: "Approved",
  posted: "Posted",
  declined: "Declined",
  failed: "Failed",
  unknown: "Outcome unknown",
  confirmed: "Confirmed",
};

export interface StampProps {
  kind: StampKind;
  /** When the stamp was made (ISO 8601). */
  at?: string;
  /** Who made it, as initials ("W.S.") or a role ("OPR"). */
  by?: string;
  /** Full stamp text, replacing the composed "APPROVED · 20 OCT 08:31 · W.S.". */
  text?: string;
  /** Play the press once on mount: used when a line moves from awaiting to posted. */
  press?: boolean;
  timeZone?: string;
  className?: string;
}

export function stampText({ kind, at, by, text, timeZone }: Pick<StampProps, "kind" | "at" | "by" | "text" | "timeZone">): string {
  if (text) return text;
  const parts = [WORD[kind]];
  if (at) parts.push(formatStampTime(at, timeZone));
  if (by) parts.push(by);
  return parts.join(" · ");
}

/** A crisp double-ruled stamp. Never rotated, never textured: it reads like a register entry. */
export function Stamp({ kind, at, by, text, press, timeZone, className }: StampProps) {
  return (
    <span className={cn("stamp", className)} data-kind={kind} data-press={press ? "" : undefined}>
      {stampText({ kind, at, by, text, timeZone })}
    </span>
  );
}
