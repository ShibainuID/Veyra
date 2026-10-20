import { Check } from "lucide-react";
import { cn } from "../../lib/cn";

export const STEPS = ["Capture", "Processing", "Review", "Confirm"] as const;

/**
 * The enrollment sequence. Numbers carry information here (the order is the procedure), so they stay.
 * The current step takes the tag yellow, like the current place in the nav.
 */
export function Stepper({ current, done = false }: { current: number; done?: boolean }) {
  return (
    <ol aria-label="Enrollment steps" className="grid grid-cols-4 gap-2 sm:gap-3">
      {STEPS.map((label, i) => {
        const complete = done || i < current;
        const active = !done && i === current;
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex min-w-0 flex-col gap-2 border-t-4 pt-3 sm:flex-row sm:items-center sm:gap-3",
              active ? "border-ink" : complete ? "border-ink" : "border-line",
            )}
          >
            <span
              className={cn(
                "figures grid size-9 flex-none place-items-center rounded-pill text-base font-bold",
                active && "bg-tag text-ink",
                complete && "bg-ink text-tag",
                !active && !complete && "border-2 border-line-strong text-muted",
              )}
            >
              {complete ? <Check aria-hidden="true" className="size-5" strokeWidth={3} /> : i + 1}
            </span>
            <span className={cn("min-w-0 truncate text-sm font-bold sm:text-base", !active && !complete && "text-muted")}>
              {label}
              <span className="sr-only">{complete ? ", done" : active ? ", current step" : ""}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
