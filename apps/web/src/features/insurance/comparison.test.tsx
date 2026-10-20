import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Recommendation } from "../finance/api";
import { buildComparison } from "./comparison";
import { ComparisonTable } from "./ComparisonTable";

const shared = [
  { text: "Pre-existing injury or illness.", terms_ref: "sample-v1 §4.1" },
  { text: "Neglect.", terms_ref: "sample-v1 §4.2" },
];
const identity = { field: "identity_status", terms_ref: "sample-v1 §2.1", text: "Confirmed identity reference.", status: "pass" as const, detail: "identity_status is confirmed" };

const results: Recommendation[] = [
  {
    product_id: "basic-mortality",
    product_name: "Basic Mortality & Accident",
    outcome: "eligible",
    reasons: [identity],
    needs_review: [],
    premium_minor: 8_736,
    deductible_minor: 24_960,
    currency: "USD",
    covered_perils: ["accidental_injury", "death"],
    exclusions: shared,
    payout_formula: { expression: "max(0, min(eligible_loss, remaining_limit) - deductible)", terms_ref: "sample-v1 §5.1" },
  },
  {
    product_id: "mortality-theft",
    product_name: "Mortality + Theft",
    outcome: "unknown",
    reasons: [
      identity,
      { field: "ownership_document", terms_ref: "sample-v1 §2.4", text: "An ownership document reference is on file.", status: "unknown", detail: "ownership_document is not on record" },
    ],
    needs_review: ["Add an ownership document reference"],
    premium_minor: 12_979,
    deductible_minor: 15_000,
    currency: "USD",
    covered_perils: ["accidental_injury", "death", "theft"],
    exclusions: [...shared, { text: "Theft without a police report.", terms_ref: "sample-v1 §4.5" }],
    payout_formula: null,
  },
  {
    product_id: "dairy-health-plus",
    product_name: "Dairy Health Plus",
    outcome: "ineligible",
    reasons: [identity, { field: "breed_category", terms_ref: "sample-v1 §2.5", text: "Dairy breeds only.", status: "fail", detail: "breed_category is beef" }],
    needs_review: [],
    premium_minor: null,
    deductible_minor: null,
    currency: "USD",
    covered_perils: ["illness", "accidental_injury"],
    exclusions: shared,
    payout_formula: null,
  },
];

describe("buildComparison", () => {
  it("aligns perils and rules across products and prints shared exclusions once", () => {
    const c = buildComparison(results);
    expect(c.perils).toEqual(["accidental_injury", "death", "theft", "illness"]);
    expect(c.rules.map((r) => r.field)).toEqual(["identity_status", "ownership_document", "breed_category"]);
    expect(c.rules[1]!.cells.map((cell) => cell?.status ?? null)).toEqual([null, "unknown", null]);
    expect(c.sharedExclusions.map((e) => e.terms_ref)).toEqual(["sample-v1 §4.1", "sample-v1 §4.2"]);
    expect(c.ownExclusions.map((list) => list.length)).toEqual([0, 1, 0]);
  });
});

describe("ComparisonTable", () => {
  it("shows each outcome with its reason, and an action only for the eligible product", () => {
    render(
      <ComparisonTable
        results={results}
        renderAction={(r) => (r.outcome === "eligible" ? <button type="button">Prepare application</button> : <span>Not available</span>)}
      />,
    );
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual([
      expect.stringContaining("Basic Mortality & Accident"),
      expect.stringContaining("Mortality + Theft"),
      expect.stringContaining("Dairy Health Plus"),
    ]);
    const outcomeRow = within(table).getByRole("rowheader", { name: "Outcome" }).closest("tr")!;
    const cells = within(outcomeRow).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Eligible");
    expect(cells[1]).toHaveTextContent("Unknown");
    expect(cells[1]).toHaveTextContent("Needs review: Add an ownership document reference");
    expect(cells[2]).toHaveTextContent("Ineligible");
    expect(cells[2]).toHaveTextContent("Rule not met: Dairy breeds only.");
    expect(cells[2]).toHaveTextContent("sample-v1 §2.5");

    const premiumRow = within(table).getByRole("rowheader", { name: "Premium" }).closest("tr")!;
    expect(within(premiumRow).getAllByRole("cell")[0]).toHaveTextContent("87.36 USD");
    expect(within(premiumRow).getAllByRole("cell")[2]).toHaveTextContent("No premium quoted");

    expect(within(table).getAllByRole("button", { name: "Prepare application" })).toHaveLength(1);
    expect(within(table).getByRole("rowheader", { name: "Exclusions in all 3" })).toBeInTheDocument();
  });
});
