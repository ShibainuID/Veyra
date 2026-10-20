import { OctagonAlert, RotateCw, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { ApiError, errorCopy } from "../lib/errors";
import { Button } from "./Button";

/* ---------- Skeleton ---------- */

export interface SkeletonProps {
  /** Text lines to draw; the last one is shorter. Ignored when `height` is set. */
  lines?: number;
  /** Draw one block of this CSS height instead of lines (for frames, rows, figures). */
  height?: string;
  width?: string;
  className?: string;
}

/** Placeholder shapes, hidden from assistive technology. Wrap with `LoadingRegion` for a label. */
export function Skeleton({ lines = 1, height, width, className }: SkeletonProps) {
  if (height) {
    return <span aria-hidden="true" className={cn("skeleton", className)} style={{ height, width: width ?? "100%" }} />;
  }
  return (
    <span aria-hidden="true" className={cn("flex flex-col gap-2", className)} style={{ width }}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton h-4" style={{ width: i === lines - 1 && lines > 1 ? "62%" : "100%" }} />
      ))}
    </span>
  );
}

/** A labelled loading region: screen readers hear the label, sighted users see the skeleton. */
export function LoadingRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/* ---------- Empty state ---------- */

export interface EmptyStateProps {
  title: string;
  /** One sentence that teaches what will appear here and how it gets there. */
  children: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  headingLevel?: 2 | 3;
  className?: string;
}

/** A dashed slot waiting to be filled, like an unstamped line. */
export function EmptyState({ title, children, icon: Icon, action, headingLevel = 2, className }: EmptyStateProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <div className={cn("rounded-panel border-2 border-dashed border-line-strong px-6 py-8 sm:px-8", className)}>
      <div className="flex max-w-[62ch] flex-col items-start gap-3">
        {Icon && <Icon aria-hidden="true" className="size-7 text-muted" strokeWidth={2} />}
        <Heading className="text-md font-bold">{title}</Heading>
        <p className="text-muted">{children}</p>
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}

/* ---------- Error notice ---------- */

const ATTENTION_CODES = new Set([
  "IDENTITY_UNCONFIRMED",
  "EVIDENCE_INCOMPLETE",
  "APPROVAL_REQUIRED",
  "APPROVAL_STALE",
  "ACTION_EXPIRED",
  "DUPLICATE_EXECUTION",
  "INVALID_STATE",
  "FORBIDDEN_ROLE",
  "UNAUTHENTICATED",
  "NOT_FOUND",
  "VALIDATION_FAILED",
]);

export interface ErrorNoticeProps {
  /** An `ApiError` (or anything thrown); its code picks the copy. */
  error?: unknown;
  /** A code to show without an error object. */
  code?: string;
  title?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}

/**
 * Plain-language copy for an API error. Codes that need a decision (stale approval, wrong role)
 * read as orange attention; failures (no connection, no funds, server errors) read as red.
 */
export function ErrorNotice({ error, code, title, onRetry, retrying, className }: ErrorNoticeProps) {
  const resolved = code ?? (error instanceof ApiError ? error.code : undefined);
  const attention = resolved !== undefined && ATTENTION_CODES.has(resolved);
  const Icon = attention ? TriangleAlert : OctagonAlert;
  return (
    <div
      role="alert"
      className={cn(
        "flex gap-3 rounded-control border-2 p-4",
        attention ? "border-uncertain bg-uncertain-soft" : "border-danger bg-danger-soft",
        className,
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn("mt-0.5 size-5 flex-none", attention ? "text-uncertain-ink" : "text-danger")}
        strokeWidth={2.25}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {title && <p className="font-bold">{title}</p>}
        <p>{errorCopy(resolved)}</p>
        {resolved && <p className="figures text-sm text-muted">Code {resolved}</p>}
        {onRetry && (
          <div className="mt-2">
            <Button variant="secondary" icon={RotateCw} onClick={onRetry} loading={retrying} loadingLabel="Trying again…">
              Try again
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
