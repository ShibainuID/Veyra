import { Ellipsis, MessageSquareText, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import { buttonClasses } from "../components/Button";
import { cn } from "../lib/cn";
import { formatMoney } from "../lib/format";
import { inMore, MoreSheet } from "./MoreSheet";
import { NAV_ITEMS, type NavItem } from "./nav";
import { RoleSwitcher } from "./RoleSwitcher";
import { TagLogo } from "./TagLogo";
import { useShellSummary, type HerdSummary } from "./use-shell-summary";

function ApprovalsBadge({ count, active }: { count: number | undefined; active: boolean }) {
  if (!count) return null;
  return (
    <span
      className={cn(
        "figures inline-grid h-6 min-w-6 place-items-center rounded-pill px-1.5 text-sm font-bold",
        active ? "bg-ink text-tag" : "bg-tag text-ink",
      )}
    >
      {count}
      <span className="sr-only"> waiting</span>
    </span>
  );
}

function WalletBalance({ summary }: { summary: HerdSummary | undefined }) {
  return (
    <div className="hidden min-w-0 items-center gap-2.5 lg:flex">
      <Wallet aria-hidden="true" className="hidden size-5 flex-none text-on-shell-muted xl:block" strokeWidth={2.25} />
      <div className="flex flex-col leading-tight whitespace-nowrap">
        <span className="text-sm text-on-shell-muted">Sandbox wallet</span>
        {summary ? (
          <span className="figures font-bold">{formatMoney(summary.wallet_balance_minor, summary.currency)}</span>
        ) : (
          <span className="figures font-bold">
            <span aria-hidden="true">—</span>
            <span className="sr-only">balance unavailable</span>
          </span>
        )}
      </div>
    </div>
  );
}

function TopNavLink({ item, pathname, count }: { item: NavItem; pathname: string; count: number | undefined }) {
  const active = item.matches(pathname);
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-12 items-center gap-2 rounded-control px-2.5 font-bold whitespace-nowrap no-underline transition-colors xl:px-4",
        active ? "bg-tag text-ink" : "text-on-shell hover:bg-shell-2",
      )}
    >
      {item.label}
      {item.badge === "approvals" && <ApprovalsBadge count={count} active={active} />}
    </Link>
  );
}

function TopBar({ pathname, summary }: { pathname: string; summary: HerdSummary | undefined }) {
  return (
    <header data-surface="shell" className="sticky top-0 z-sticky bg-shell text-on-shell">
      <div className="flex h-16 items-center gap-2 px-4 lg:h-(--shell-height) xl:px-6">
        <Link
          to="/"
          aria-label="VEYRA, go to the herd"
          className="flex min-h-11 flex-none items-center gap-2.5 rounded-control px-1 no-underline lg:mr-2 xl:mr-6"
        >
          <TagLogo className="h-8 w-[26px]" />
          <span className="text-md font-bold tracking-[0.06em]">VEYRA</span>
        </Link>
        <nav aria-label="Primary" className="hidden items-center gap-0.5 lg:flex xl:gap-1">
          {NAV_ITEMS.map((item) => (
            <TopNavLink key={item.to} item={item} pathname={pathname} count={summary?.pending_approvals} />
          ))}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2 xl:gap-4">
          <Link
            to="/ask"
            aria-current={pathname === "/ask" ? "page" : undefined}
            className={buttonClasses("shell", "md", cn("px-3", pathname === "/ask" && "border-tag"))}
          >
            <MessageSquareText aria-hidden="true" className="size-5" strokeWidth={2.25} />
            {/* Icon-only between 1024 and 1280px, where the full bar is tightest. */}
            <span className="lg:max-xl:sr-only">Ask</span>
          </Link>
          <WalletBalance summary={summary} />
          <RoleSwitcher />
        </div>
      </div>
    </header>
  );
}

function BottomTabs({ pathname, count }: { pathname: string; count: number | undefined }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = inMore(pathname);
  return (
    <>
    <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} pathname={pathname} />
    <nav
      aria-label="Primary"
      data-surface="shell"
      className="fixed inset-x-0 bottom-0 z-sticky bg-shell pb-[env(safe-area-inset-bottom)] text-on-shell lg:hidden"
    >
      <ul className="grid h-(--tabbar-height) grid-cols-5 gap-1 px-1 py-1">
        {NAV_ITEMS.filter((item) => item.inTabs).map((item) => {
          const active = item.matches(pathname);
          const Icon = item.icon;
          return (
            <li key={item.to} className="min-w-0">
              <Link
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex h-full flex-col items-center justify-center gap-0.5 rounded-control text-xs font-bold no-underline",
                  active ? "bg-tag text-ink" : "text-on-shell hover:bg-shell-2",
                )}
              >
                <Icon aria-hidden="true" className="size-5" strokeWidth={2.25} />
                <span className="truncate">{item.label}</span>
                {item.badge === "approvals" && count ? (
                  <span
                    className={cn(
                      "figures absolute top-0.5 left-[calc(50%+6px)] inline-grid h-5 min-w-5 place-items-center rounded-pill px-1 text-xs font-bold",
                      active ? "bg-ink text-tag" : "bg-tag text-ink",
                    )}
                  >
                    {count}
                    <span className="sr-only"> waiting</span>
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
        <li className="min-w-0">
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen(true)}
            className={cn(
              "relative flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-control text-xs font-bold",
              moreActive ? "bg-tag text-ink" : "text-on-shell hover:bg-shell-2",
            )}
          >
            <Ellipsis aria-hidden="true" className="size-5" strokeWidth={2.25} />
            <span className="truncate">More</span>
            {moreActive && <span className="sr-only">, current section</span>}
          </button>
        </li>
      </ul>
    </nav>
    </>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const { data: summary } = useShellSummary();
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-tooltip rounded-control bg-tag px-4 py-3 font-bold text-ink no-underline focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to main content
      </a>
      <TopBar pathname={pathname} summary={summary} />
      <main
        id="main"
        tabIndex={-1}
        className="flex flex-1 flex-col pb-[calc(var(--tabbar-height)+env(safe-area-inset-bottom))] outline-none lg:pb-0"
      >
        <Outlet />
      </main>
      <BottomTabs pathname={pathname} count={summary?.pending_approvals} />
    </div>
  );
}
