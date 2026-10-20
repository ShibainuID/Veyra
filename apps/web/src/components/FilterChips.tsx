import { Check } from "lucide-react";
import { cn } from "../lib/cn";

export interface FilterOption<V extends string = string> {
  value: V;
  label: string;
  count?: number;
  disabled?: boolean;
}

export interface FilterChipsProps<V extends string = string> {
  /** Names the group for assistive technology ("Filter herd"). */
  label: string;
  options: readonly FilterOption<V>[];
  value: V;
  onChange: (value: V) => void;
  className?: string;
}

/** One-of-many filter toggles. Pressed state shows as fill plus a check, not color alone. */
export function FilterChips<V extends string = string>({ label, options, value, onChange, className }: FilterChipsProps<V>) {
  return (
    <div role="group" aria-label={label} className={cn("flex flex-wrap gap-2", className)}>
      {options.map((option) => {
        const pressed = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={pressed}
            disabled={option.disabled}
            onClick={() => {
              if (!pressed) onChange(option.value);
            }}
            className={cn(
              "inline-flex min-h-11 items-center gap-2 rounded-control border-2 px-4 text-base font-bold",
              "transition-[background-color,color,border-color] duration-(--dur-fast) ease-out-quart",
              "disabled:cursor-not-allowed disabled:border-line disabled:text-muted",
              pressed
                ? "border-ink bg-ink text-white"
                : "border-ink bg-bg text-ink hover:bg-surface-2 active:bg-line",
            )}
          >
            {pressed && <Check aria-hidden="true" className="-ml-1 size-4" strokeWidth={3} />}
            <span>{option.label}</span>
            {option.count !== undefined && (
              <span className={cn("figures text-sm", pressed ? "text-white" : "text-muted")}>{option.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
