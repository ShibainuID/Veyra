import { Lock, Stamp as StampIcon } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/use-media-query";
import { formatMoney, lineNumber } from "../lib/format";
import { Money } from "./figures";
import { Button } from "./Button";
import { EarTag, type EarTagState } from "./EarTag";
import { ErrorNotice } from "./feedback";
import { PassbookLine, type PassbookLineData } from "./PassbookLine";
import { Provenance, type Source } from "./Provenance";

export interface PassbookAnimal {
  id: string;
  name: string;
  tagState: EarTagState;
  /** "Bali cattle · F · 24–30 mo"; may carry provenance chips. */
  description?: ReactNode;
}

export interface PassbookFact {
  label: string;
  value: ReactNode;
  source?: Source;
}

export interface PassbookSummary {
  currency?: string;
  exposureLowMinor: number;
  exposureHighMinor: number;
  insuredMinor: number;
}

export interface PassbookDecision {
  /** Sandbox wallet balance if the awaiting line posts. */
  balanceAfterMinor: number;
  currency?: string;
  onApprove: () => void;
  onDecline: () => void;
  approving?: boolean;
  declining?: boolean;
  /** False for operators and vets: the button stays visible but cannot be used. */
  canApprove?: boolean;
  blockedReason?: string;
  error?: unknown;
}

export interface PassbookPanelProps {
  animal: PassbookAnimal;
  facts?: readonly PassbookFact[];
  summary?: PassbookSummary;
  lines: readonly PassbookLineData[];
  decision?: PassbookDecision;
  /**
   * Replaces the built-in decision bar for the awaiting line with a richer review (the shared
   * ActionReview). Rendered only while a line is awaiting.
   */
  decisionSlot?: ReactNode;
  /** Positioning for the slot's wrapper, such as sticky to the bottom of a scrolling panel. */
  decisionSlotClassName?: string;
  /** Heading level for the animal name: 2 in a side panel, 3 inside a page section. */
  headingLevel?: 2 | 3;
  timeZone?: string;
  className?: string;
}

const IDENTITY_WORDS: Record<EarTagState, string> = {
  confirmed: "identity confirmed",
  pending: "identity pending review",
  none: "no identity assigned",
};

/**
 * The selected tag's passbook: a big tag, the key facts, exposure against cover, every line in
 * order, and a decision bar for the line that waits on the manager's stamp.
 */
export function PassbookPanel({
  animal,
  facts,
  summary,
  lines,
  decision,
  decisionSlot,
  decisionSlotClassName,
  headingLevel = 2,
  timeZone,
  className,
}: PassbookPanelProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const Sub = headingLevel === 2 ? "h3" : "h4";
  const headingId = useId();
  const awaiting = lines.find((line) => line.status === "awaiting");
  const currency = summary?.currency ?? "USD";
  const uninsuredLow = summary ? Math.max(0, summary.exposureLowMinor - summary.insuredMinor) : 0;
  const uninsuredHigh = summary ? Math.max(0, summary.exposureHighMinor - summary.insuredMinor) : 0;
  // On a short screen (a 1024×768 tablet) the header compacts so the waiting line and its stamp
  // slot stay above the decision bar: a smaller tag, one meta line, and a one-row exposure strip.
  const compact = useMediaQuery("(max-height: 820px)");
  const cell = compact ? "py-2" : "py-3";
  const listRef = useRef<HTMLOListElement>(null);

  // Fade the top edge once lines scroll under it, so a cut-off earlier line reads as "more above".
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const update = () => {
      if (list.scrollTop > 0) list.setAttribute("data-scrolled", "");
      else list.removeAttribute("data-scrolled");
    };
    update();
    list.addEventListener("scroll", update, { passive: true });
    return () => list.removeEventListener("scroll", update);
  }, [lines.length]);

  return (
    <section aria-labelledby={headingId} className={cn("flex min-h-0 flex-col bg-bg", className)}>
      <div className={cn("flex flex-col", compact ? "gap-3 px-5 pt-4 pb-3" : "gap-5 px-5 pt-6 pb-5")} data-compact={compact || undefined}>
        <div className={cn("flex items-center", compact ? "gap-4" : "gap-5")}>
          <EarTag animalId={animal.id} state={animal.tagState} size={compact ? "md" : "xl"} />
          <div className="flex min-w-0 flex-col gap-1">
            <Heading id={headingId} className="text-xl font-bold">
              {animal.name}
            </Heading>
            {compact ? (
              <p className="truncate text-sm text-muted">
                <span className="figures whitespace-nowrap text-ink">{animal.id}</span> · {IDENTITY_WORDS[animal.tagState]}
              </p>
            ) : (
              <p className="text-muted">
                <span className="figures whitespace-nowrap text-ink">{animal.id}</span>
                <br />
                {IDENTITY_WORDS[animal.tagState]}
              </p>
            )}
          </div>
        </div>
        {/* Full width under the tag, so breed, age, and weight with their sources read on as few lines as possible. */}
        {animal.description && <div className={cn("text-muted", !compact && "-mt-2")}>{animal.description}</div>}

        {facts && facts.length > 0 && (
          <dl className="grid grid-cols-2 gap-x-5">
            {facts.map((fact) => (
              <div key={fact.label} className="flex min-w-0 flex-col gap-1 border-t border-line py-3">
                <dt className="text-sm text-muted">{fact.label}</dt>
                <dd className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="figures text-base font-bold sm:text-md">{fact.value}</span>
                  {fact.source && <Provenance source={fact.source} />}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {summary && (
          <dl
            className={cn(
              "grid border-y-2 border-ink",
              // Compact: each figure keeps to one line, so the strip is a single row of three cells.
              compact ? "grid-cols-[auto_auto_minmax(0,1fr)] [&_dd]:text-sm [&_dd]:whitespace-nowrap" : "grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]",
            )}
          >
            <div className={cn("flex flex-col gap-1 pr-3", cell)}>
              <dt className="text-sm text-muted">Exposure</dt>
              <dd className="figures font-bold"><Money low={summary.exposureLowMinor} high={summary.exposureHighMinor} currency={currency} /></dd>
            </div>
            <div className={cn("flex flex-col gap-1 border-l border-line px-3", cell)}>
              <dt className="text-sm text-muted">Insured</dt>
              <dd className="figures font-bold"><Money minor={summary.insuredMinor} currency={currency} whole /></dd>
            </div>
            <div className={cn("flex flex-col gap-1 border-l border-line pl-3", cell)}>
              <dt className="text-sm text-muted">Uninsured</dt>
              <dd className={cn("figures font-bold", uninsuredHigh > 0 && "text-danger")}>
                {uninsuredHigh === 0 ? <Money minor={0} currency={currency} whole /> : <Money low={uninsuredLow} high={uninsuredHigh} currency={currency} />}
              </dd>
            </div>
          </dl>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-baseline justify-between px-5 pb-2">
          <Sub className="text-md font-bold">Passbook</Sub>
          <span className="text-sm text-muted">
            <span className="figures">{lines.length}</span> {lines.length === 1 ? "line" : "lines"}
          </span>
        </div>
        {lines.length === 0 ? (
          <p className="mx-5 mb-5 rounded-control border-2 border-dashed border-line-strong p-4 text-muted">
            Nothing has posted yet. Enrollment writes the first line.
          </p>
        ) : (
          <ol ref={listRef} className="pb-list relative min-h-0 flex-1 overflow-y-auto border-t border-line px-1 [scrollbar-gutter:stable]">
            {lines.map((line) => (
              <PassbookLine key={line.id} {...line} timeZone={timeZone} />
            ))}
          </ol>
        )}
      </div>

      {awaiting && decisionSlot && (
        <div className={cn("border-t-2 border-ink bg-bg px-[22px] pt-4 pb-5", decisionSlotClassName)}>{decisionSlot}</div>
      )}
      {awaiting && decision && !decisionSlot && (
        <DecisionBar line={awaiting} decision={decision} currency={decision.currency ?? currency} />
      )}
    </section>
  );
}

function DecisionBar({ line, decision, currency }: { line: PassbookLineData; decision: PassbookDecision; currency: string }) {
  const canApprove = decision.canApprove ?? true;
  const busy = Boolean(decision.approving || decision.declining);
  return (
    <div
      className={cn(
        "flex flex-col gap-3 border-t-2 border-ink bg-bg px-[22px] pt-4 pb-5",
        "max-tab:sticky max-tab:bottom-[calc(var(--tabbar-height)+env(safe-area-inset-bottom))] max-tab:z-sticky max-tab:shadow-[0_-6px_16px_oklch(0.18_0.005_260/0.1)]",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span>
          Balance after line <span className="figures">{lineNumber(line.number)}</span>
        </span>
        <span className="figures text-md font-bold whitespace-nowrap">{formatMoney(decision.balanceAfterMinor, currency)}</span>
      </div>
      {!canApprove && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Lock aria-hidden="true" className="size-4 flex-none" strokeWidth={2.25} />
          {decision.blockedReason ?? "Only a manager can approve. Switch role to Manager."}
        </p>
      )}
      {decision.error !== undefined && decision.error !== null && <ErrorNotice error={decision.error} />}
      {/* Decline sits apart from Approve: 32px beside it, or 24px below it on a phone. */}
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:gap-0">
        <Button
          variant="primary"
          size="decision"
          icon={StampIcon}
          className="sm:flex-1"
          onClick={decision.onApprove}
          loading={decision.approving}
          loadingLabel="Approving…"
          disabled={!canApprove || busy}
        >
          Approve and stamp
        </Button>
        <Button
          variant="danger"
          size="decision"
          className="flex-none sm:ml-8"
          onClick={decision.onDecline}
          loading={decision.declining}
          loadingLabel="Declining…"
          disabled={busy}
        >
          Decline
        </Button>
      </div>
    </div>
  );
}
