import { describe, expect, it } from "vitest";
import { parseMoneyInput } from "./money-input";

describe("parseMoneyInput", () => {
  it("converts whole and decimal amounts to minor units without float error", () => {
    expect(parseMoneyInput("1200")).toBe(120_000);
    expect(parseMoneyInput("1,200.50")).toBe(120_050);
    expect(parseMoneyInput("0.1")).toBe(10);
    expect(parseMoneyInput("19.99")).toBe(1_999);
    expect(parseMoneyInput(".5")).toBe(50);
    expect(parseMoneyInput(" 2,496.00 USD ")).toBe(249_600);
  });

  it("rejects values that aren't a plain non-negative amount", () => {
    for (const bad of ["", "abc", "-5", "1.234", "12,34", "1..2", ".", "1e3"]) {
      expect(parseMoneyInput(bad)).toBeNull();
    }
  });

  it("follows the currency's exponent", () => {
    expect(parseMoneyInput("1500", "JPY")).toBe(1_500);
    expect(parseMoneyInput("15.5", "JPY")).toBeNull();
  });
});
