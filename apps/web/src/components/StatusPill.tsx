import { CircleCheck, CircleMinus, CircleX, Hourglass, TriangleAlert, type LucideIcon } from "lucide-react";
import { cn } from "../lib/cn";

export type StatusTone = "ok" | "danger" | "uncertain" | "neutral" | "awaiting";

const TONE_CLASS: Record<StatusTone, string> = {
  ok: "bg-ok-soft text-ok",
  danger: "bg-danger-soft text-danger",
  uncertain: "bg-uncertain-soft text-uncertain-ink",
  neutral: "border-2 border-line text-muted",
  awaiting: "bg-tag-soft text-await-ink border border-tag-edge",
};

const TONE_ICON: Record<StatusTone, LucideIcon> = {
  ok: CircleCheck,
  danger: CircleX,
  uncertain: TriangleAlert,
  neutral: CircleMinus,
  awaiting: Hourglass,
};

export interface StatusPillProps {
  tone: StatusTone;
  label: string;
  /**
   * A shorter word shown where a narrow table can't fit the full label (beside the passbook at
   * 1024px). The full label stays in the accessible name.
   */
  shortLabel?: string;
  /** Replace the tone's default icon. State is always icon plus text, never color alone. */
  icon?: LucideIcon;
  className?: string;
}

export function StatusPill({ tone, label, shortLabel, icon, className }: StatusPillProps) {
  const Icon = icon ?? TONE_ICON[tone];
  return (
    <span
      className={cn(
        "inline-flex h-8 max-w-full items-center gap-1.5 rounded-pill px-3 text-sm font-bold whitespace-nowrap",
        TONE_CLASS[tone],
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-4 flex-none" strokeWidth={2.25} />
      <span className={cn("truncate", shortLabel && "pill-label-full")}>{label}</span>
      {shortLabel && (
        <span className="pill-label-short" aria-hidden="true">
          {shortLabel}
        </span>
      )}
    </span>
  );
}
