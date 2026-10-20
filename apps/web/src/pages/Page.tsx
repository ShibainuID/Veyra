import type { ReactNode } from "react";
import { cn } from "../lib/cn";

/** The page frame inside <main>: one column, 16px gutters on phones, capped on wide screens. */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8", className)}>{children}</div>;
}
