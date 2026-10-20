import { Cctv, ClipboardList, FileCheck2, ScanLine, ScrollText, Stamp, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Whether a pathname belongs to this section (animal pages belong to the herd). */
  matches: (pathname: string) => boolean;
  /** Shown in the bottom tab bar below 1024px; the rest open from its "More" sheet. */
  inTabs: boolean;
  badge?: "approvals";
}

const under = (...prefixes: string[]) => (pathname: string) =>
  prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/herd", label: "Herd", icon: ClipboardList, matches: under("/herd", "/animals"), inTabs: true },
  { to: "/enroll", label: "Enroll", icon: ScanLine, matches: under("/enroll"), inTabs: true },
  { to: "/monitor", label: "Monitor", icon: Cctv, matches: under("/monitor", "/alerts"), inTabs: true },
  { to: "/approvals", label: "Approvals", icon: Stamp, matches: under("/approvals"), inTabs: true, badge: "approvals" },
  { to: "/claims", label: "Claims", icon: FileCheck2, matches: under("/claims"), inTabs: false },
  { to: "/audit", label: "Audit", icon: ScrollText, matches: under("/audit"), inTabs: false },
];
