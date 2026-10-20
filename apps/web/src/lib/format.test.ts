import { describe, expect, it } from "vitest";
import { ApiError, ERROR_COPY, FALLBACK_ERROR_COPY, errorCopy } from "./errors";
import {
  formatAbsolute,
  formatClockSeconds,
  formatCountdown,
  formatMoney,
  formatMoneyRange,
  formatRange,
  formatRelative,
  formatStampTime,
  initials,
  lineNumber,
  tagNumber,
} from "./format";

const MINUS = "−";

describe("formatMoney", () => {
  it("converts minor units to major with two decimals and the currency code", () => {
    expect(formatMoney(249_600, "USD")).toBe("2,496.00 USD");
    expect(formatMoney(8_736)).toBe("87.36 USD");
    expect(formatMoney(5)).toBe("0.05 USD");
    expect(formatMoney(0)).toBe("0.00 USD");
  });

  it("groups thousands", () => {
    expect(formatMoney(1_000_000)).toBe("10,000.00 USD");
    expect(formatMoney(123_456_789_00)).toBe("123,456,789.00 USD");
  });

  it("prints negatives with a true minus sign", () => {
    expect(formatMoney(-8_736)).toBe(`${MINUS}87.36 USD`);
  });

  it("signs credits and debits when asked", () => {
    expect(formatMoney(8_736, "USD", { signed: true })).toBe("+87.36 USD");
    expect(formatMoney(-8_736, "USD", { signed: true })).toBe(`${MINUS}87.36 USD`);
    expect(formatMoney(0, "USD", { signed: true })).toBe("0.00 USD");
  });

  it("can drop the code or the fraction", () => {
    expect(formatMoney(991_264, "USD", { bare: true })).toBe("9,912.64");
    expect(formatMoney(249_650, "USD", { whole: true })).toBe("2,497 USD");
  });

  it("upper-cases the currency code", () => {
    expect(formatMoney(100, "usd")).toBe("1.00 USD");
  });

  it("rejects fractional minor units", () => {
    expect(() => formatMoney(87.36)).toThrow(TypeError);
  });
});

describe("formatMoneyRange", () => {
  it("prints whole-unit ranges with an en dash", () => {
    expect(formatMoneyRange(249_600, 291_200, "USD")).toBe("2,496–2,912 USD");
  });

  it("rounds outward so the range never narrows", () => {
    expect(formatMoneyRange(249_650, 291_210, "USD")).toBe("2,496–2,913 USD");
  });

  it("prints exact ranges with decimals", () => {
    expect(formatMoneyRange(249_600, 291_200, "USD", { exact: true })).toBe("2,496.00–2,912.00 USD");
  });

  it("orders reversed bounds", () => {
    expect(formatMoneyRange(291_200, 249_600)).toBe("2,496–2,912 USD");
  });
});

describe("formatRange", () => {
  it("prints a measured range with its unit", () => {
    expect(formatRange(480, 560, "kg")).toBe("480–560 kg");
    expect(formatRange(24, 24, "mo")).toBe("24 mo");
  });
});

describe("tagNumber", () => {
  it("takes the last three digits of the animal ID", () => {
    expect(tagNumber("animal-demo-001")).toBe("001");
    expect(tagNumber("animal-demo-1042")).toBe("042");
  });

  it("pads short numbers", () => {
    expect(tagNumber("animal-demo-7")).toBe("007");
  });

  it("falls back to the last three characters when there are no digits", () => {
    expect(tagNumber("animal-abc")).toBe("ABC");
  });
});

describe("lineNumber", () => {
  it("prints three digits", () => {
    expect(lineNumber(4)).toBe("004");
    expect(lineNumber(120)).toBe("120");
  });
});

describe("dates", () => {
  const iso = "2026-10-20T02:42:00Z";

  it("formats absolute time in a given zone", () => {
    expect(formatAbsolute(iso, "Asia/Jakarta")).toBe("20 Oct 2026, 09:42");
    expect(formatAbsolute(iso, "UTC")).toBe("20 Oct 2026, 02:42");
  });

  it("formats stamp time in capitals", () => {
    expect(formatStampTime("2026-10-20T01:31:00Z", "Asia/Jakarta")).toBe("20 OCT 08:31");
  });

  it("formats relative time", () => {
    const now = Date.parse(iso);
    expect(formatRelative(now - 10_000, now)).toBe("just now");
    expect(formatRelative(now - 2 * 60_000, now)).toBe("2 min ago");
    expect(formatRelative(now - 3 * 3_600_000, now)).toBe("3 h ago");
    expect(formatRelative(now - 26 * 3_600_000, now)).toBe("yesterday");
    expect(formatRelative(now - 4 * 86_400_000, now)).toBe("4 days ago");
    expect(formatRelative(now + 5 * 60_000, now)).toBe("in 5 min");
  });

  it("formats countdowns", () => {
    expect(formatCountdown(24 * 60_000 + 51_000)).toBe("24:51");
    expect(formatCountdown(3_723_000)).toBe("1:02:03");
    expect(formatCountdown(-5_000)).toBe("00:00");
  });

  it("makes stamp initials", () => {
    expect(initials("Wahyu Santoso")).toBe("W.S.");
  });
});

describe("error copy", () => {
  it("maps documented codes to plain copy", () => {
    expect(errorCopy("IDENTITY_UNCONFIRMED")).toBe("Confirm this animal's identity before any financial action.");
    expect(errorCopy("EVIDENCE_INCOMPLETE")).toBe("Some required evidence is missing.");
    expect(errorCopy("APPROVAL_STALE")).toBe("The details changed after approval. Review the new version.");
    expect(errorCopy("FORBIDDEN_ROLE")).toBe("Your role can't do this. Switch to Manager to approve.");
  });

  it("has copy for every code it knows", () => {
    for (const [code, copy] of Object.entries(ERROR_COPY)) {
      expect(copy, code).toMatch(/\.$/);
    }
  });

  it("falls back for unknown or missing codes", () => {
    expect(errorCopy("SOMETHING_NEW")).toBe(FALLBACK_ERROR_COPY);
    expect(errorCopy(undefined)).toBe("Something went wrong. Try again.");
  });

  it("parses the API error envelope", () => {
    const err = ApiError.fromEnvelope(409, {
      error: { code: "APPROVAL_STALE", message: "Payload hash changed.", details: { action_id: "act-1" } },
    });
    expect(err.status).toBe(409);
    expect(err.code).toBe("APPROVAL_STALE");
    expect(err.message).toBe("Payload hash changed.");
    expect(err.details).toEqual({ action_id: "act-1" });
    expect(err.copy).toBe(ERROR_COPY.APPROVAL_STALE);
    expect(err.isClientError).toBe(true);
  });

  it("survives bodies that aren't envelopes", () => {
    expect(ApiError.fromEnvelope(404, "<html>").code).toBe("NOT_FOUND");
    expect(ApiError.fromEnvelope(502, null).code).toBe("HTTP_ERROR");
  });
});

describe("formatClockSeconds", () => {
  it("keeps the seconds, so a 30 s window inside one minute reads as two times", () => {
    expect(formatClockSeconds("2026-10-20T09:31:00Z", "UTC")).toBe("09:31:00");
    expect(formatClockSeconds("2026-10-20T09:31:30Z", "UTC")).toBe("09:31:30");
  });
});
