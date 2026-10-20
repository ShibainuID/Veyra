import { Cpu, FileText, FlaskConical, Radio, type LucideIcon } from "lucide-react";
import { cn } from "../lib/cn";

export type Source = "live" | "prototype" | "simulated" | "documented";

const STYLE: Record<Source, { className: string; icon: LucideIcon; meaning: string }> = {
  live: { className: "bg-ok text-white border-2 border-ok", icon: Radio, meaning: "from a live provider" },
  prototype: { className: "border-2 border-ink text-ink", icon: Cpu, meaning: "from a prototype model" },
  simulated: { className: "border-2 border-dashed border-muted text-muted", icon: FlaskConical, meaning: "simulated, not observed" },
  documented: { className: "bg-surface-2 border-2 border-surface-2 text-ink", icon: FileText, meaning: "from a document on file" },
};

export interface ProvenanceProps {
  source: Source;
  className?: string;
}

/** Where a figure came from. Always visible next to the figure, never hover-only. */
export function Provenance({ source, className }: ProvenanceProps) {
  const { className: tone, icon: Icon, meaning } = STYLE[source];
  return (
    <span
      className={cn(
        "inline-flex h-7 flex-none items-center gap-1 rounded-pill px-2.5 text-sm font-bold whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" strokeWidth={2.25} />
      <span className="sr-only">Source: </span>
      {source}
      <span className="sr-only">, {meaning}</span>
    </span>
  );
}
