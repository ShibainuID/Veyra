import { ArrowRight, Bot } from "lucide-react";
import { Fragment, useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { PassbookPanel } from "../../components/PassbookPanel";
import { Provenance } from "../../components/Provenance";
import { agentHref } from "../../lib/agent-link";
import { asSource, rangeText, sexWord, tagStateFor } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { ActionReview } from "../actions/ActionReview";
import { usePassport, type Passport } from "../passport/api";
import { toPassbookLines, usePressedLines } from "./lines";
import { awaitingScrollTop } from "./scroll";

export interface AnimalPassbookProps {
  animalId: string;
  /** 2 in the herd's side panel; 3 when the passbook is a section of the passport. */
  headingLevel?: 2 | 3;
  /** Show the "Open passport" link (the herd panel). */
  passportLink?: boolean;
  /** Where the decision bar sticks: the bottom of the panel, or above the phone tab bar. */
  stickTo?: "panel" | "window";
  className?: string;
}

export function animalDescription(passport: Passport, extra?: ReactNode): ReactNode {
  const { animal } = passport;
  const parts: ReactNode[] = [<span key="breed">{animal.breed}</span>, <span key="sex">{sexWord(animal.sex)}</span>];
  const age = rangeText(animal.age);
  if (age && animal.age) {
    parts.push(
      <span key="age" className="inline-flex items-center gap-1.5">
        <span className="figures">{age}</span>
        <Provenance source={asSource(animal.age.source)} />
      </span>,
    );
  }
  const weight = rangeText(animal.weight);
  if (weight && animal.weight) {
    parts.push(
      <span key="weight" className="inline-flex items-center gap-1.5">
        <span className="figures">{weight}</span>
        <Provenance source={asSource(animal.weight.source)} />
      </span>,
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
        {parts.map((part, i) => (
          <Fragment key={i}>
            {i > 0 && <span aria-hidden="true">·</span>}
            {part}
          </Fragment>
        ))}
      </p>
      {extra}
    </div>
  );
}

function PassbookSkeleton() {
  return (
    <LoadingRegion label="Loading the passbook">
      <div className="flex flex-col gap-5 px-5 pt-6 pb-5">
        <div className="flex items-center gap-5">
          <Skeleton height="96px" width="134px" />
          <Skeleton lines={3} width="50%" />
        </div>
        <Skeleton height="64px" />
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} height="72px" />
        ))}
      </div>
    </LoadingRegion>
  );
}

/** One animal's passbook from its passport: header, exposure against cover, lines, and the waiting decision. */
export function AnimalPassbook({ animalId, headingLevel = 2, passportLink = false, stickTo = "panel", className }: AnimalPassbookProps) {
  const { data: passport, isPending, error, refetch, isRefetching } = usePassport(animalId);
  const pressed = usePressedLines(animalId, passport?.passbook.lines);
  const rootRef = useRef<HTMLDivElement>(null);
  const awaitingNo = passport?.passbook.lines.find((line) => line.status === "awaiting")?.no;

  // When the lines scroll inside a fixed-height panel, seat the waiting line whole at the list's
  // bottom, just above the decision bar. Fonts and the decision bar settle after first paint and
  // change the list's height, so re-align on every resize until the reader scrolls themselves.
  useEffect(() => {
    const root = rootRef.current;
    if (!root || awaitingNo === undefined) return;
    const line = root.querySelector<HTMLElement>('.pb-line[data-status="awaiting"]');
    const list = line?.closest<HTMLElement>(".pb-list");
    if (!line || !list) return;
    let frame = 0;
    let userScrolled = false;
    const align = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (userScrolled || list.scrollHeight <= list.clientHeight) return;
        const lineOffset = line.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
        list.scrollTop = awaitingScrollTop({ lineOffset, lineHeight: line.offsetHeight, listHeight: list.clientHeight });
      });
    };
    const stop = () => {
      userScrolled = true;
    };
    align();
    void document.fonts?.ready.then(align);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(align);
    observer?.observe(list);
    observer?.observe(line);
    list.addEventListener("wheel", stop, { passive: true });
    list.addEventListener("touchstart", stop, { passive: true });
    list.addEventListener("keydown", stop);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      list.removeEventListener("wheel", stop);
      list.removeEventListener("touchstart", stop);
      list.removeEventListener("keydown", stop);
    };
  }, [animalId, awaitingNo, isPending]);

  if (isPending) return <PassbookSkeleton />;
  if (error || !passport) {
    return (
      <div className="p-5">
        <ErrorNotice error={error} title="This passbook couldn't load" onRetry={() => void refetch()} retrying={isRefetching} />
      </div>
    );
  }

  const { animal, passbook } = passport;
  const summary = passbook.summary;
  const awaiting = passbook.lines.find((line) => line.status === "awaiting" && line.action_id);

  return (
    <div ref={rootRef} className={cn("flex min-h-0 flex-col", className)}>
    <PassbookPanel
      className="flex-1"
      headingLevel={headingLevel}
      animal={{
        id: animal.id,
        name: animal.name,
        tagState: tagStateFor(animal.identity_status),
        description: animalDescription(
          passport,
          passportLink ? (
            <span className="flex flex-wrap items-center gap-x-5">
              <Link to={`/animals/${animal.id}`} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-ink">
                Open passport
                <ArrowRight aria-hidden="true" className="size-4" strokeWidth={2.5} />
              </Link>
              {animal.coverage.status === "none" && (
                <Link to={agentHref(animal.id, "find_insurance")} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-ink">
                  <Bot aria-hidden="true" className="size-4" strokeWidth={2.5} />
                  Find insurance
                  <span className="sr-only"> for {animal.name} with the VEYRA agent</span>
                </Link>
              )}
            </span>
          ) : null,
        ),
      }}
      summary={
        summary.exposure_low_minor != null && summary.exposure_high_minor != null
          ? {
              currency: summary.currency ?? "USD",
              exposureLowMinor: summary.exposure_low_minor,
              exposureHighMinor: summary.exposure_high_minor,
              insuredMinor: summary.insured_minor,
            }
          : undefined
      }
      lines={toPassbookLines(passbook.lines, animal.id, pressed)}
      decisionSlot={
        awaiting ? <ActionReview key={awaiting.action_id} actionId={awaiting.action_id!} variant="bar" lineNo={awaiting.no} /> : undefined
      }
      decisionSlotClassName={cn(
        "sticky bottom-0 z-sticky shadow-[0_-8px_16px_-8px_oklch(0.18_0.005_260/0.18)]",
        stickTo === "window" && "max-lg:bottom-[calc(var(--tabbar-height)+env(safe-area-inset-bottom))]",
      )}
    />
    </div>
  );
}
