import { useEffect, useRef } from "react";
import { useLocation } from "react-router";

/** Monitor and an alert's drawer are one screen: opening the drawer keeps the page where it was. */
const sameScreen = (a: string, b: string) => {
  const monitor = (p: string) => p === "/monitor" || p.startsWith("/alerts/");
  return a === b || (monitor(a) && monitor(b));
};

/**
 * A new screen opens at its top, or at its `#section` once that section has rendered (sections
 * appear after their data loads, so the hash is retried briefly). Search-only changes, such as
 * selecting a line on Approvals, keep the scroll position.
 */
export function useScrollOnNavigate(): void {
  const { pathname, hash } = useLocation();
  const previous = useRef(pathname);

  useEffect(() => {
    const from = previous.current;
    previous.current = pathname;
    if (!hash && sameScreen(from, pathname)) return;
    if (!hash) {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      return;
    }
    const id = decodeURIComponent(hash.slice(1));
    let tries = 0;
    const timer = window.setInterval(() => {
      const target = document.getElementById(id);
      if (target || ++tries > 20) {
        window.clearInterval(timer);
        target?.scrollIntoView({ block: "start" });
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [pathname, hash]);
}
