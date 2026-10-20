import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import type { PassbookAmount, PassbookLineData } from "../../components/PassbookLine";
import type { StampKind } from "../../components/Stamp";
import { initials } from "../../lib/format";
import { ActionLineSummary } from "../actions/ActionReview";
import type { PassbookLineOut } from "../passport/api";

/** Where a line's subject lives in the app, if it has a screen of its own. */
export function subjectHref(line: Pick<PassbookLineOut, "subject_type" | "subject_id">, animalId: string): { to: string; label: string } | null {
  switch (line.subject_type) {
    case "alert":
      return { to: `/alerts/${line.subject_id}`, label: "Open alert" };
    case "policy":
    case "policy_application":
      return { to: `/animals/${animalId}/insurance`, label: "See coverage" };
    case "claim":
      return { to: `/claims/${line.subject_id}`, label: "Open claim" };
    default:
      return null;
  }
}

function amountFor(line: PassbookLineOut): PassbookAmount | undefined {
  if (line.amount_minor == null) return undefined;
  const currency = line.currency ?? "USD";
  const isPremiumPayment = line.title.startsWith("Premium payment");
  // Only a premium that is paid (or about to be) moves the sandbox wallet.
  if (isPremiumPayment && (line.status === "awaiting" || line.event_type === "action.executed")) {
    return { minor: -line.amount_minor, currency };
  }
  let label = "Amount";
  if (line.event_type.startsWith("valuation")) label = "Valued";
  else if (line.event_type.includes("policy")) label = "Insured";
  else if (line.event_type.startsWith("incident")) label = "Est. loss";
  else if (line.event_type.startsWith("claim")) label = "Claimed";
  else if (line.event_type.startsWith("action")) label = isPremiumPayment ? "Premium" : "Premium quoted";
  return { minor: line.amount_minor, currency, label };
}

function stampBy(line: PassbookLineOut): string | undefined {
  const by = line.stamp?.by;
  if (!by) return undefined;
  return line.actor.type === "user" ? initials(by) : by;
}

export function lineKey(line: Pick<PassbookLineOut, "no">): string {
  return `line-${line.no}`;
}

/** API passbook lines to the passbook component's lines. Lines keep their number as identity. */
export function toPassbookLines(lines: readonly PassbookLineOut[], animalId: string, pressed: ReadonlySet<number>): PassbookLineData[] {
  return lines.map((line) => {
    const link = subjectHref(line, animalId);
    const awaitingAction = line.status === "awaiting" && line.action_id;
    const detail =
      line.detail || link || awaitingAction ? (
        <>
          {line.detail && <span>{line.detail}</span>}
          {link && (
            <>
              {line.detail && " · "}
              <Link to={link.to} className="inline-flex items-center gap-1 font-bold text-ink">
                {link.label}
                <ArrowRight aria-hidden="true" className="size-3.5" strokeWidth={2.5} />
              </Link>
            </>
          )}
          {awaitingAction && <ActionLineSummary actionId={line.action_id!} />}
        </>
      ) : undefined;
    return {
      id: lineKey(line),
      number: line.no,
      at: line.at,
      title: line.title,
      detail,
      amount: amountFor(line),
      status: line.status,
      expiresAt: line.expires_at ?? undefined,
      stamp: line.stamp
        ? { kind: line.stamp.kind as StampKind, at: line.stamp.at, by: stampBy(line), press: pressed.has(line.no) }
        : undefined,
    };
  });
}

/**
 * The signature move: when a line that was awaiting comes back stamped (or a stamped line is
 * written while the passbook is open), its stamp presses onto that exact line. Computed during
 * render from the previous lines, so the stamp mounts already pressing.
 */
export function usePressedLines(animalId: string, lines: readonly PassbookLineOut[] | undefined): ReadonlySet<number> {
  const [snapshot, setSnapshot] = useState<{
    animalId: string;
    lines: readonly PassbookLineOut[] | undefined;
    pressed: ReadonlySet<number>;
  }>({ animalId, lines, pressed: new Set() });

  if (snapshot.lines !== lines || snapshot.animalId !== animalId) {
    let pressed: ReadonlySet<number> = new Set();
    if (lines && snapshot.lines && snapshot.animalId === animalId) {
      const before = new Map(snapshot.lines.map((line) => [line.no, line]));
      const next = new Set<number>();
      for (const line of lines) {
        if (!line.stamp || line.status === "awaiting") continue;
        const previous = before.get(line.no);
        if (!previous || previous.status === "awaiting" || !previous.stamp) next.add(line.no);
      }
      pressed = next;
    }
    setSnapshot({ animalId, lines, pressed });
    return pressed;
  }
  return snapshot.pressed;
}
