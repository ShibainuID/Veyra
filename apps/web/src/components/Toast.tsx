import { CircleCheck, Info, OctagonAlert, X, type LucideIcon } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { IconButton } from "./Button";

export type ToastTone = "ok" | "danger" | "neutral";

export interface ToastInput {
  title: string;
  body?: string;
  tone?: ToastTone;
  /** Milliseconds before it dismisses itself; 0 keeps it until dismissed. */
  duration?: number;
}

interface ToastItem extends Required<Omit<ToastInput, "body">> {
  id: number;
  body?: string;
}

interface ToastApi {
  show: (toast: ToastInput) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const ICON: Record<ToastTone, LucideIcon> = { ok: CircleCheck, danger: OctagonAlert, neutral: Info };
const ICON_CLASS: Record<ToastTone, string> = { ok: "text-ok", danger: "text-danger", neutral: "text-ink" };

/** Toasts announce through one polite live region that is always mounted. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) window.clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const show = useCallback(
    ({ title, body, tone = "neutral", duration = 6000 }: ToastInput) => {
      const id = nextId.current++;
      setToasts((all) => [...all.slice(-3), { id, title, body, tone, duration }]);
      if (duration > 0) timers.current.set(id, window.setTimeout(() => dismiss(id), duration));
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const map = timers.current;
    return () => map.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-[calc(var(--tabbar-height)+env(safe-area-inset-bottom)+16px)] z-toast flex flex-col items-end gap-2 lg:right-6 lg:bottom-6 lg:left-auto"
      >
        {toasts.map((toast) => {
          const Icon = ICON[toast.tone];
          return (
            <div
              key={toast.id}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-panel border-2 border-ink bg-bg py-3 pr-2 pl-4 shadow-raised"
            >
              <Icon aria-hidden="true" className={cn("mt-0.5 size-5 flex-none", ICON_CLASS[toast.tone])} strokeWidth={2.25} />
              <div className="min-w-0 flex-1 py-0.5">
                <p className="font-bold">{toast.title}</p>
                {toast.body && <p className="text-muted">{toast.body}</p>}
              </div>
              <IconButton label="Dismiss notification" icon={X} onClick={() => dismiss(toast.id)} />
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
