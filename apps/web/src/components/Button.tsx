import { LoaderCircle, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";
import { cn } from "../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "shell";
export type ButtonSize = "md" | "decision";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-control font-bold whitespace-nowrap select-none no-underline " +
  "transition-[background-color,color,border-color,translate] duration-(--dur-fast) ease-out-quart " +
  "active:translate-y-px disabled:cursor-not-allowed disabled:active:translate-y-0";

const VARIANT: Record<ButtonVariant, string> = {
  // Black with a tag-yellow label: the world's primary action.
  primary:
    "bg-ink text-tag border-2 border-ink hover:bg-shell-2 hover:border-shell-2 active:bg-shell " +
    "disabled:bg-surface-2 disabled:border-surface-2 disabled:text-muted",
  secondary:
    "bg-bg text-ink border-2 border-ink hover:bg-surface-2 active:bg-line " +
    "disabled:border-line disabled:text-muted disabled:bg-bg",
  danger:
    "bg-bg text-danger border-2 border-danger hover:bg-danger-soft active:border-danger-pressed active:text-danger-pressed " +
    "disabled:border-line disabled:text-muted disabled:bg-bg",
  ghost: "text-ink border-2 border-transparent hover:bg-surface-2 active:bg-line disabled:text-muted disabled:bg-transparent",
  shell: "text-on-shell border-2 border-shell-line hover:bg-shell-2 active:bg-shell disabled:text-on-shell-muted",
};

/** Primary actions are 48px, others 44px; the passbook decision is 52px. */
function sizeClasses(variant: ButtonVariant, size: ButtonSize): string {
  if (size === "decision") return "min-h-[52px] px-5 text-base sm:text-md";
  if (variant === "primary") return "min-h-12 px-5 text-base";
  if (variant === "ghost") return "min-h-11 px-3 text-base";
  return "min-h-11 px-4 text-base";
}

export function buttonClasses(variant: ButtonVariant = "secondary", size: ButtonSize = "md", className?: string): string {
  return cn(BASE, VARIANT[variant], sizeClasses(variant, size), className);
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  /** Shows a spinner, disables the button, and swaps in `loadingLabel` ("Approving…"). */
  loading?: boolean;
  loadingLabel?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  loading = false,
  loadingLabel,
  disabled,
  className,
  children,
  type = "button",
  onClick,
  ...rest
}: ButtonProps) {
  // Loading keeps the variant's colors (it is busy, not unavailable): the button is
  // aria-disabled and ignores clicks rather than taking the grey disabled look.
  return (
    <button
      type={type}
      className={buttonClasses(variant, size, cn(loading && "cursor-progress active:translate-y-0", className))}
      disabled={disabled}
      aria-disabled={loading || undefined}
      aria-busy={loading || undefined}
      onClick={(event) => {
        if (loading) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      {...rest}
    >
      {loading ? (
        <LoaderCircle aria-hidden="true" className="size-5 flex-none motion-safe:animate-spin" strokeWidth={2.5} />
      ) : (
        Icon && <Icon aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
      )}
      <span>{loading ? (loadingLabel ?? children) : children}</span>
    </button>
  );
}

export interface ButtonLinkProps extends Omit<LinkProps, "className"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  className?: string;
}

/** Navigation that looks like a button (for example "Prepare application"). */
export function ButtonLink({ variant = "secondary", size = "md", icon: Icon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonClasses(variant, size, className)} {...rest}>
      {Icon && <Icon aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />}
      <span>{children as ReactNode}</span>
    </Link>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label" | "children"> {
  /** Required: the accessible name, since the button shows only an icon. */
  label: string;
  icon: LucideIcon;
  variant?: Extract<ButtonVariant, "ghost" | "secondary" | "shell">;
}

/** A 44px square icon button. */
export function IconButton({ label, icon: Icon, variant = "ghost", className, type = "button", ...rest }: IconButtonProps) {
  return (
    <button type={type} aria-label={label} className={cn(BASE, VARIANT[variant], "size-11 flex-none", className)} {...rest}>
      <Icon aria-hidden="true" className="size-5" strokeWidth={2.25} />
    </button>
  );
}
