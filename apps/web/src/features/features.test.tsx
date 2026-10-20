import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { eventTitle, genericTitle } from "./audit/event-title";
import { matchesFilter, serverFilters } from "./herd/HerdPage";
import { usePressedLines } from "./passbook/lines";
import type { HerdItem, PassbookLineOut } from "./passport/api";
import { parseKg, parsePriceMinor, valueRange } from "./passport/valuation";

describe("eventTitle", () => {
  it("uses the passbook's words for agent actions and their results", () => {
    expect(eventTitle("action.proposed", { action_type: "POLICY_APPLICATION" })).toBe("Policy application prepared");
    expect(eventTitle("action.approved", { action_type: "PREMIUM_PAYMENT" })).toBe("Premium payment approved");
    expect(eventTitle("action.executed", { action_type: "PREMIUM_PAYMENT", status: "succeeded" })).toBe("Premium payment paid");
    expect(eventTitle("action.executed", { action_type: "POLICY_APPLICATION", status: "succeeded" })).toBe("Policy application sent");
    expect(eventTitle("action.executed", { action_type: "CLAIM_SUBMISSION", status: "unknown" })).toBe("Claim submission outcome unknown");
  });

  it("names policies, alerts, and valuations", () => {
    expect(eventTitle("seed.policy_created", { product_id: "basic-mortality" })).toBe("Policy active · Basic Mortality & Accident");
    expect(eventTitle("alert.created", { kind: "reduced_movement" })).toBe("Alert · reduced movement");
    expect(eventTitle("alert.created", { kind: "observation_quality" })).toBe("Observation quality warning");
    expect(eventTitle("valuation.confirmed", {})).toBe("Valued");
    expect(eventTitle("enrollment.confirmed", { decision: "link_existing" })).toBe("Enrollment linked to this animal");
  });

  it("falls back to the event type in plain words", () => {
    expect(eventTitle("wallet.topped_up")).toBe("Wallet topped up");
    expect(genericTitle("seed.something_new")).toBe("Something new");
    expect(eventTitle("action.proposed", {})).toBe("Action prepared");
  });
});

const line = (no: number, status: PassbookLineOut["status"], stamped: boolean): PassbookLineOut => ({
  no,
  at: "2026-10-20T05:00:00Z",
  kind: status === "awaiting" ? "awaiting" : "event",
  event_type: "action.approved",
  title: "Policy application",
  detail: null,
  actor: { type: "user", id: "u", name: "W. Santoso" },
  amount_minor: null,
  currency: null,
  stamp: stamped ? { kind: "approved", by: "W. Santoso", at: "2026-10-20T05:01:00Z" } : null,
  action_id: "act-1",
  subject_type: "agent_action",
  subject_id: "act-1",
  status,
  expires_at: null,
  payload_hash_prefix: null,
});

describe("usePressedLines", () => {
  it("presses the stamp on the line that was awaiting, and on new stamped lines, but not on first load", () => {
    const first = [line(1, "posted", true), line(2, "awaiting", false)];
    const { result, rerender } = renderHook(({ lines }) => usePressedLines("animal-demo-001", lines), {
      initialProps: { lines: first },
    });
    expect([...result.current]).toEqual([]);

    const after = [line(1, "posted", true), line(2, "posted", true), line(3, "posted", true)];
    rerender({ lines: after });
    expect([...result.current].sort()).toEqual([2, 3]);
  });

  it("does not press when switching animals", () => {
    const { result, rerender } = renderHook(({ id, lines }) => usePressedLines(id, lines), {
      initialProps: { id: "a", lines: [line(1, "awaiting", false)] },
    });
    rerender({ id: "b", lines: [line(1, "posted", true)] });
    expect(result.current.size).toBe(0);
  });
});

describe("valuation arithmetic", () => {
  it("parses prices to minor units and refuses bad input", () => {
    expect(parsePriceMinor("5.20")).toBe(520);
    expect(parsePriceMinor("5")).toBe(500);
    expect(parsePriceMinor("5,2")).toBe(520);
    expect(parsePriceMinor("5.205")).toBeNull();
    expect(parsePriceMinor("0")).toBeNull();
    expect(parsePriceMinor("abc")).toBeNull();
    expect(parseKg("512.5")).toBe(512.5);
    expect(parseKg("")).toBeNull();
  });

  it("floors weight × price at each end like the server", () => {
    expect(valueRange(480, 560, 520)).toEqual({ low: 249_600, high: 291_200 });
    expect(valueRange(512.5, 512.7, 333)).toEqual({ low: 170_662, high: 170_729 });
  });
});

describe("herd filters", () => {
  const item = (overrides: Partial<HerdItem>): HerdItem =>
    ({
      id: "animal-demo-001",
      identity_status: "confirmed",
      coverage: { status: "none", policy_id: null, product_id: null, policy_status: null },
      alerts: { open_count: 0, kinds: [] },
      awaiting_approval_count: 0,
      ...overrides,
    }) as HerdItem;

  it("sends coverage and alert filters to the server and narrows the rest on the client", () => {
    expect(serverFilters("uncovered", " Sari ")).toEqual({ coverage: "none", q: "Sari" });
    expect(serverFilters("alerts", "")).toEqual({ alerts: "open" });
    expect(serverFilters("awaiting", "")).toEqual({});
    expect(matchesFilter(item({ awaiting_approval_count: 1 }), "awaiting")).toBe(true);
    expect(matchesFilter(item({}), "awaiting")).toBe(false);
    expect(matchesFilter(item({ identity_status: "pending_review" }), "identity")).toBe(true);
  });
});
