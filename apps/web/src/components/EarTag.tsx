import { cn } from "../lib/cn";
import { tagNumber } from "../lib/format";

export type EarTagState = "confirmed" | "pending" | "none";
export type EarTagSize = "sm" | "md" | "xl";

export interface EarTagProps {
  /** Animal ID ("animal-demo-001"); the tag shows its last three digits. */
  animalId?: string;
  /** The printed number, if it should not be derived from the ID. */
  number?: string;
  /** Solid tag: identity confirmed. Dashed outline: pending review. Grey: unassigned track. */
  state: EarTagState;
  size?: EarTagSize;
  className?: string;
}

/**
 * The tag outline in a 112×80 box: a narrow neck carrying the punched button hole, flaring to a
 * wide panel with heavily rounded bottom corners, like a molded livestock ear tag.
 */
const OUTLINE =
  "M41 3H71Q83 3 85.5 14C87.5 23 108 24 108 41V57Q108 77 88 77H24Q4 77 4 57V41C4 24 24.5 23 26.5 14Q29 3 41 3Z";
const HOLE = "M62.5 16A6.5 6.5 0 1 0 49.5 16A6.5 6.5 0 1 0 62.5 16Z";

export function earTagLabel(state: EarTagState, number: string): string {
  if (state === "none") return "No ear tag, unassigned track";
  if (state === "pending") return `Ear tag ${number}, identity pending review`;
  return `Ear tag ${number}, identity confirmed`;
}

export function EarTag({ animalId, number, state, size = "sm", className }: EarTagProps) {
  const printed = number ?? (animalId ? tagNumber(animalId) : "---");
  return (
    <span
      role="img"
      aria-label={earTagLabel(state, printed)}
      className={cn("ear-tag", className)}
      data-state={state}
      data-size={size}
    >
      <svg viewBox="0 0 112 80" aria-hidden="true" focusable="false">
        {/* Fill with the hole punched through, then the outline (dashed when pending), then a solid hole ring. */}
        <path className="ear-tag-fill" d={`${OUTLINE}${HOLE}`} fillRule="evenodd" />
        <path className="ear-tag-edge" d={OUTLINE} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        <path className="ear-tag-hole" d={HOLE} vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="ear-tag-number" aria-hidden="true">
        {state === "none" ? "no tag" : printed}
      </span>
    </span>
  );
}
