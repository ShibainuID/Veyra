import { Info } from "lucide-react";
import { cn } from "../lib/cn";

/** The one wording for every estimate and indicative value: the passport, the valuation, the herd's exposure. */
export const NOT_GUARANTEED = "Estimated, not guaranteed · indicative value is not an insurer-agreed value or a payout";

/** A small legible line under an estimate or indicative value. Plain words, never hover-only. */
export function NotGuaranteed({ className }: { className?: string }) {
  return (
    <p className={cn("flex items-start gap-1.5 text-sm text-muted", className)}>
      <Info aria-hidden="true" className="mt-0.5 size-4 flex-none" strokeWidth={2.25} />
      <span>{NOT_GUARANTEED}</span>
    </p>
  );
}
