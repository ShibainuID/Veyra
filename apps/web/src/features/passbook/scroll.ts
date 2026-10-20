export interface AwaitingScrollInput {
  /** The line's top, measured from the top of the list's scrolled content. */
  lineOffset: number;
  lineHeight: number;
  /** The list's visible height. */
  listHeight: number;
  /** Breathing room kept between the line and the list's edge. */
  gap?: number;
}

/**
 * Where to scroll the passbook list so the awaiting line sits whole at its bottom edge, just
 * above the decision bar. A line taller than the list aligns to the top instead, so its number
 * and title stay readable.
 */
export function awaitingScrollTop({ lineOffset, lineHeight, listHeight, gap = 8 }: AwaitingScrollInput): number {
  if (lineHeight + gap * 2 > listHeight) return Math.max(0, Math.round(lineOffset - gap));
  return Math.max(0, Math.round(lineOffset + lineHeight + gap - listHeight));
}
