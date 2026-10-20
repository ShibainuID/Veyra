import { MessageSquareText, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Link } from "react-router";
import { IconButton } from "../components/Button";
import { cn } from "../lib/cn";
import { NAV_ITEMS } from "./nav";
import { DemoReset } from "./DemoReset";
import { RoleSwitcher } from "./RoleSwitcher";

export const MORE_ITEMS = [
  ...NAV_ITEMS.filter((item) => !item.inTabs),
  { to: "/ask", label: "Ask", icon: MessageSquareText, matches: (p: string) => p === "/ask", inTabs: false },
];

/** Whether the current page lives behind the "More" tab. */
export function inMore(pathname: string): boolean {
  return MORE_ITEMS.some((item) => item.matches(pathname));
}

/**
 * The phone's "More" sheet: the screens that don't fit the bottom tabs, and the demo role.
 * A native modal dialog, so focus is trapped, Esc closes it, and focus returns to the tab.
 */
export function MoreSheet({ open, onClose, pathname }: { open: boolean; onClose: () => void; pathname: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

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
      data-surface="shell"
      aria-labelledby={titleId}
      className="sheet"
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-2">
        <h2 id={titleId} className="text-md font-bold">
          More
        </h2>
        <IconButton label="Close" icon={X} variant="shell" onClick={onClose} />
      </div>
      <nav aria-label="More screens">
        <ul className="flex flex-col gap-1 px-2">
          {MORE_ITEMS.map((item) => {
            const active = item.matches(pathname);
            const Icon = item.icon;
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  onClick={onClose}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-14 items-center gap-3 rounded-control px-3 text-base font-bold no-underline",
                    active ? "bg-tag text-ink" : "text-on-shell hover:bg-shell-2",
                  )}
                >
                  <Icon aria-hidden="true" className="size-5" strokeWidth={2.25} />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="mt-2 flex items-center justify-between gap-3 border-t border-shell-line px-4 pt-4 pb-[calc(16px+env(safe-area-inset-bottom))]">
        <span className="text-on-shell-muted">Acting as</span>
        <span className="flex items-center gap-2">
          <DemoReset compact />
          <RoleSwitcher />
        </span>
      </div>
    </dialog>
  );
}
