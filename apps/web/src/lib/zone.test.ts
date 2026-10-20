import { describe, expect, it } from "vitest";
import { formatClockSeconds, localizeWindowText, zoneLabel } from "./format";

describe("local zone", () => {
  it("prints the zone the way the server does", () => {
    expect(zoneLabel("2026-10-20T07:32:54Z")).toMatch(/^UTC([+-]\d{1,2}(:\d{2})?)?$/);
  });

  it("restates a server UTC window in the viewer's local time", () => {
    const start = "2026-10-20T07:32:54Z";
    const end = "2026-10-20T07:33:24Z";
    const text = "Movement 78% below Sari's earlier window on Pen A (07:32:54–07:33:24 UTC). Not a diagnosis.";
    expect(localizeWindowText(text, start, end)).toBe(
      `Movement 78% below Sari's earlier window on Pen A (${formatClockSeconds(start)}–${formatClockSeconds(end)} ${zoneLabel(start)}). Not a diagnosis.`,
    );
    expect(localizeWindowText(text, start, end, "UTC")).toBe(text);
    expect(localizeWindowText("No window here.", start, end)).toBe("No window here.");
  });
});
