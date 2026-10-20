import { CircleCheck, CircleDashed } from "lucide-react";
import type { ReactNode } from "react";
import { Mono } from "../../components/figures";
import { cn } from "../../lib/cn";
import type { ChecklistItem } from "../finance/api";

export interface EvidenceChecklistProps {
  items: readonly ChecklistItem[];
  /** How to supply a missing item: a link, a form, or a checkbox. */
  renderFix?: (item: ChecklistItem) => ReactNode;
  className?: string;
}

/**
 * Each requirement of the product's claim terms, present or missing. State is an icon plus a
 * word, never color alone, and every missing item says where to fix it.
 */
export function EvidenceChecklist({ items, renderFix, className }: EvidenceChecklistProps) {
  const missing = items.filter((item) => item.status === "missing").length;
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <p className={cn("font-bold", missing ? "text-danger" : "text-ok")}>
        {missing === 0 ? (
          "Every requirement is on file."
        ) : (
          <>
            <Mono>{missing}</Mono> of <Mono>{items.length}</Mono> requirements {missing === 1 ? "is" : "are"} missing.
          </>
        )}
      </p>
      <ul className="flex flex-col border-t-2 border-ink">
        {items.map((item) => {
          const present = item.status === "present";
          const Icon = present ? CircleCheck : CircleDashed;
          const fix = present ? null : renderFix?.(item);
          return (
            <li key={item.key} className="flex gap-3 border-b border-line py-3" data-status={item.status}>
              <Icon
                aria-hidden="true"
                className={cn("mt-0.5 size-5 flex-none", present ? "text-ok" : "text-danger")}
                strokeWidth={2.25}
              />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="font-bold">{item.label}</span>
                  <span className={cn("text-sm font-bold", present ? "text-ok" : "text-danger")}>{present ? "Present" : "Missing"}</span>
                </p>
                {item.detail ? (
                  <span className={cn("text-sm", present ? "text-muted" : "text-ink")}>{item.detail}</span>
                ) : (
                  present && item.ref && <Mono className="text-sm text-muted">{item.ref}</Mono>
                )}
                {fix && <div className="text-sm">{fix}</div>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
