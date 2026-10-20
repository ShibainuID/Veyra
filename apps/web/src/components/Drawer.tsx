import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { IconButton } from "./Button";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** A short line under the title (for example the alert window and animal ID). */
  description?: ReactNode;
  children: ReactNode;
  /** Pinned below the scrolling body (decision buttons). */
  footer?: ReactNode;
  /** Replaces the body padding (for content that brings its own, such as a passbook). */
  bodyClassName?: string;
  className?: string;
}

/**
 * A right-hand drawer on the native modal <dialog>: the browser traps focus, Esc closes it, and
 * focus returns to the opener. Clicking the backdrop also closes it.
 */
export function Drawer({ open, onClose, title, description, children, footer, bodyClassName, className }: DrawerProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={cn("drawer", className)}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-start gap-3 border-b-2 border-ink px-6 pt-5 pb-4">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-bold">
              {title}
            </h2>
            {description && (
              <div id={descriptionId} className="mt-1 text-muted">
                {description}
              </div>
            )}
          </div>
          <IconButton label="Close" icon={X} variant="secondary" onClick={onClose} className="-mr-2" />
        </header>
        <div className={cn("min-h-0 flex-1 overflow-y-auto", bodyClassName ?? "px-6 py-5")}>{children}</div>
        {footer && <footer className="border-t-2 border-ink px-6 pt-4 pb-[calc(16px+env(safe-area-inset-bottom))]">{footer}</footer>}
      </div>
    </dialog>
  );
}
