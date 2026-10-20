import { useEffect, useState } from "react";

/**
 * How many journey stamps the traveling tag carries: the furthest step the visitor has reached,
 * and every step before it. A step that was reached stays stamped, so scrolling back never
 * un-stamps the tag, and jumping straight to a later step stamps the ones it skipped.
 */
export function stampCount(order: readonly string[], reached: ReadonlySet<string>): number {
  let furthest = -1;
  order.forEach((id, index) => {
    if (reached.has(id)) furthest = index;
  });
  return furthest + 1;
}

/**
 * Watches the journey steps (by element ID) and returns how many are stamped. A step counts as
 * reached once its top passes 60% of the viewport, or when it is already above the viewport (a
 * visitor who lands lower on the page). With `allAtOnce` (reduced motion) or without
 * IntersectionObserver, every stamp shows from the start.
 */
export function useStampCount(ids: readonly string[], allAtOnce: boolean): number {
  const [reached, setReached] = useState<ReadonlySet<string>>(() => new Set());
  const observable = typeof IntersectionObserver !== "undefined";

  useEffect(() => {
    if (allAtOnce || !observable) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const hits = entries
          .filter((entry) => entry.isIntersecting || entry.boundingClientRect.top < 0)
          .map((entry) => entry.target.id);
        if (hits.length === 0) return;
        setReached((prev) => {
          if (hits.every((id) => prev.has(id))) return prev;
          const next = new Set(prev);
          hits.forEach((id) => next.add(id));
          return next;
        });
      },
      { rootMargin: "0px 0px -40% 0px" },
    );
    ids.forEach((id) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [ids, allAtOnce, observable]);

  if (allAtOnce || !observable) return ids.length;
  return stampCount(ids, reached);
}
