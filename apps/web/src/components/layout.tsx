import { useId, type ReactNode } from "react";
import { cn } from "../lib/cn";

export interface PageHeaderProps {
  title: ReactNode;
  /** One line of context: counts, the farm, the record's ID. */
  meta?: ReactNode;
  actions?: ReactNode;
  /** Leading visual, such as the animal's ear tag on the passport. */
  lead?: ReactNode;
  className?: string;
}

/** The page's h1. No kicker above it: the heading carries its own weight. */
export function PageHeader({ title, meta, actions, lead, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-4 pb-6 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="flex min-w-0 items-center gap-4">
        {lead}
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-xl font-bold">{title}</h1>
          {meta && <div className="text-muted">{meta}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </header>
  );
}

export interface SectionProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** An anchor for `#links` to this section. */
  anchor?: string;
}

/** An h2 section: more space above the heading than below it. */
export function Section({ title, description, actions, children, className, anchor }: SectionProps) {
  const id = useId();
  return (
    <section id={anchor} aria-labelledby={id} className={cn("mt-12 first:mt-0", className)}>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id={id} className="text-lg font-bold">
            {title}
          </h2>
          {description && <p className="max-w-[70ch] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
