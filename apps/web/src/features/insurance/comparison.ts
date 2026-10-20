/**
 * Turns three per-product recommendation results into the rows of one comparison: perils and
 * eligibility rules are aligned across products, and exclusions shared by every product are
 * printed once.
 */
import type { Recommendation, RuleReason } from "../finance/api";

export const PERIL_LABEL: Record<string, string> = {
  death: "Death",
  accidental_injury: "Accidental injury",
  theft: "Theft",
  illness: "Illness",
};

const RULE_LABEL: Record<string, string> = {
  identity_status: "Confirmed identity",
  age_months: "Age",
  valuation_confirmed: "Confirmed valuation",
  ownership_document: "Ownership document",
  breed_category: "Breed",
  vet_health_check_days: "Recent vet health check",
};

export function humanize(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function perilLabel(peril: string): string {
  return PERIL_LABEL[peril] ?? humanize(peril);
}

export function ruleLabel(field: string): string {
  return RULE_LABEL[field] ?? humanize(field);
}

export interface RuleRow {
  field: string;
  label: string;
  /** One entry per product, in product order; null when that product has no such rule. */
  cells: (RuleReason | null)[];
}

export interface Comparison {
  perils: string[];
  rules: RuleRow[];
  /** Exclusions every product carries (matched on terms reference). */
  sharedExclusions: { text: string; terms_ref: string }[];
  /** Per product, the exclusions not in the shared set. */
  ownExclusions: { text: string; terms_ref: string }[][];
}

function union(lists: string[][]): string[] {
  const seen: string[] = [];
  for (const list of lists) for (const item of list) if (!seen.includes(item)) seen.push(item);
  return seen;
}

export function buildComparison(results: readonly Recommendation[]): Comparison {
  const perils = union(results.map((r) => r.covered_perils));
  const fields = union(results.map((r) => r.reasons.map((reason) => reason.field)));
  const rules = fields.map((field) => ({
    field,
    label: ruleLabel(field),
    cells: results.map((r) => r.reasons.find((reason) => reason.field === field) ?? null),
  }));
  const sharedRefs = results.length
    ? results[0]!.exclusions
        .map((e) => e.terms_ref)
        .filter((ref) => results.every((r) => r.exclusions.some((e) => e.terms_ref === ref)))
    : [];
  return {
    perils,
    rules,
    sharedExclusions: results.length ? results[0]!.exclusions.filter((e) => sharedRefs.includes(e.terms_ref)) : [],
    ownExclusions: results.map((r) => r.exclusions.filter((e) => !sharedRefs.includes(e.terms_ref))),
  };
}

/** The rule that keeps an ineligible product from being offered. */
export function failingRule(result: Recommendation): RuleReason | undefined {
  return result.reasons.find((reason) => reason.status === "fail");
}

export const OUTCOME_LABEL: Record<Recommendation["outcome"], string> = {
  eligible: "Eligible",
  ineligible: "Ineligible",
  unknown: "Unknown",
};
