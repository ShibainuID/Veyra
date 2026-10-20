import { CircleCheck, CircleHelp, CircleMinus, CircleX, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Money } from "../../components/figures";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { cn } from "../../lib/cn";
import type { Recommendation, RuleReason } from "../finance/api";
import { buildComparison, failingRule, OUTCOME_LABEL, perilLabel } from "./comparison";

const OUTCOME_TONE: Record<Recommendation["outcome"], StatusTone> = {
  eligible: "ok",
  ineligible: "danger",
  unknown: "uncertain",
};

const OUTCOME_RULE: Record<Recommendation["outcome"], string> = {
  eligible: "border-t-ok",
  ineligible: "border-t-danger",
  unknown: "border-t-uncertain",
};

const RULE_STATUS: Record<RuleReason["status"], { icon: LucideIcon; word: string; className: string }> = {
  pass: { icon: CircleCheck, word: "Pass", className: "text-ok" },
  fail: { icon: CircleX, word: "Fail", className: "text-danger" },
  unknown: { icon: CircleHelp, word: "Unknown", className: "text-uncertain-ink" },
};

function TermsRef({ value }: { value: string }) {
  return <span className="figures text-sm whitespace-nowrap text-muted">{value}</span>;
}

/** The outcome pill plus the reason in words: the failing rule, or what needs review. */
export function OutcomeCell({ result }: { result: Recommendation }) {
  const failing = failingRule(result);
  return (
    <div className="flex flex-col items-start gap-2">
      <StatusPill tone={OUTCOME_TONE[result.outcome]} label={OUTCOME_LABEL[result.outcome]} />
      {result.outcome === "ineligible" && failing && (
        <p className="text-sm">
          Rule not met: {failing.text} <TermsRef value={failing.terms_ref} />
        </p>
      )}
      {result.outcome === "unknown" && result.needs_review.length > 0 && (
        <p className="text-sm">Needs review: {result.needs_review.join("; ")}</p>
      )}
      {result.outcome === "eligible" && <p className="text-sm text-muted">Every rule passes.</p>}
    </div>
  );
}

export function RuleCell({ reason }: { reason: RuleReason | null }) {
  if (!reason) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <CircleMinus aria-hidden="true" className="size-4 flex-none" strokeWidth={2.25} />
        Not a rule for this product
      </p>
    );
  }
  const status = RULE_STATUS[reason.status];
  const Icon = status.icon;
  return (
    <div className="flex gap-2">
      <Icon aria-hidden="true" className={cn("mt-0.5 size-5 flex-none", status.className)} strokeWidth={2.25} />
      <div className="min-w-0">
        <p>
          <span className={cn("font-bold", status.className)}>{status.word}</span> · {reason.text}
        </p>
        <p className="text-sm text-muted">
          {reason.detail} · <TermsRef value={reason.terms_ref} />
        </p>
      </div>
    </div>
  );
}

function PerilCell({ covered }: { covered: boolean }) {
  return covered ? (
    <span className="flex items-center gap-2 font-bold">
      <CircleCheck aria-hidden="true" className="size-5 flex-none text-ok" strokeWidth={2.25} />
      Covered
    </span>
  ) : (
    <span className="flex items-center gap-2 text-muted">
      <CircleMinus aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
      Not covered
    </span>
  );
}

function MoneyCell({ minor, currency, suffix, none }: { minor: number | null; currency: string; suffix?: string; none: string }) {
  if (minor === null) return <span className="text-muted">{none}</span>;
  return (
    <span className="text-md font-bold">
      <Money minor={minor} currency={currency} />
      {suffix && <span className="font-sans text-base font-regular text-muted"> {suffix}</span>}
    </span>
  );
}

function PayoutCell({ formula }: { formula: Recommendation["payout_formula"] }) {
  const expression = formula && typeof formula.expression === "string" ? formula.expression : null;
  if (!expression) return <span className="text-muted">Not stated in the sample terms</span>;
  return (
    <div className="flex flex-col gap-1">
      <code className="figures text-sm break-words">{expression}</code>
      {typeof formula?.terms_ref === "string" && <TermsRef value={formula.terms_ref} />}
    </div>
  );
}

export interface ComparisonTableProps {
  results: readonly Recommendation[];
  /** What each product's column ends with (the prepare button, or why there is none). */
  renderAction: (result: Recommendation) => ReactNode;
}

interface Row {
  key: string;
  header: ReactNode;
  cell: (result: Recommendation, index: number) => ReactNode;
  /** Printed once across every product (shared exclusions). */
  spanning?: ReactNode;
}

/**
 * A real comparison: products are columns, and every row lines up the same term across them.
 * Below 720px each product stacks as its own block with the same rows, labelled.
 */
export function ComparisonTable({ results, renderAction }: ComparisonTableProps) {
  const comparison = buildComparison(results);
  const rows: Row[] = [
    { key: "outcome", header: "Outcome", cell: (r) => <OutcomeCell result={r} /> },
    {
      key: "premium",
      header: "Premium",
      cell: (r) => <MoneyCell minor={r.premium_minor} currency={r.currency} suffix="a year" none="No premium quoted" />,
    },
    {
      key: "deductible",
      header: "Deductible",
      cell: (r) => <MoneyCell minor={r.deductible_minor} currency={r.currency} suffix="per claim" none="Not quoted" />,
    },
    ...comparison.perils.map<Row>((peril) => ({
      key: `peril-${peril}`,
      header: (
        <>
          <span className="block text-sm font-regular text-muted">Covered peril</span>
          {perilLabel(peril)}
        </>
      ),
      cell: (r) => <PerilCell covered={r.covered_perils.includes(peril)} />,
    })),
    ...comparison.rules.map<Row>((rule) => ({
      key: `rule-${rule.field}`,
      header: (
        <>
          <span className="block text-sm font-regular text-muted">Eligibility rule</span>
          {rule.label}
        </>
      ),
      cell: (_r, i) => <RuleCell reason={rule.cells[i] ?? null} />,
    })),
    {
      key: "exclusions-shared",
      header: `Exclusions in all ${results.length}`,
      cell: () => null,
      spanning: (
        <ul className="grid gap-x-8 gap-y-2 lg:grid-cols-2">
          {comparison.sharedExclusions.map((e) => (
            <li key={e.terms_ref}>
              {e.text} <TermsRef value={e.terms_ref} />
            </li>
          ))}
        </ul>
      ),
    },
    {
      key: "exclusions-own",
      header: "Further exclusions",
      cell: (_r, i) => {
        const own = comparison.ownExclusions[i] ?? [];
        if (own.length === 0) return <span className="text-muted">None beyond the shared list</span>;
        return (
          <ul className="flex flex-col gap-2">
            {own.map((e) => (
              <li key={e.terms_ref}>
                {e.text} <TermsRef value={e.terms_ref} />
              </li>
            ))}
          </ul>
        );
      },
    },
    { key: "payout", header: "Payout formula", cell: (r) => <PayoutCell formula={r.payout_formula} /> },
  ];

  return (
    <>
      <div className="hidden md:block">
        <table className="cmp w-full table-fixed border-collapse">
          <caption className="sr-only">Sample products compared for this animal</caption>
          <colgroup>
            <col className="w-[17%]" />
            {results.map((r) => (
              <col key={r.product_id} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <td />
              {results.map((r) => (
                <th key={r.product_id} scope="col" className={cn("border-t-4 px-4 pt-4 pb-3 text-left align-bottom", OUTCOME_RULE[r.outcome])}>
                  <span className="block text-md font-bold">{r.product_name}</span>
                  <span className="figures block text-sm font-regular text-muted">{r.product_id}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t border-line first:border-t-2 first:border-ink">
                <th scope="row" className="py-4 pr-4 text-left align-top font-bold">
                  {row.header}
                </th>
                {row.spanning ? (
                  <td colSpan={results.length} className="px-4 py-4 align-top">
                    {row.spanning}
                  </td>
                ) : (
                  results.map((r, i) => (
                    <td key={r.product_id} className="px-4 py-4 align-top">
                      {row.cell(r, i)}
                    </td>
                  ))
                )}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-ink">
              <td />
              {results.map((r) => (
                <td key={r.product_id} className="px-4 pt-5 align-top">
                  {renderAction(r)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      <ol className="flex flex-col gap-10 md:hidden" aria-label="Sample products compared for this animal">
        {results.map((r, i) => (
          <li key={r.product_id} className={cn("border-t-4", OUTCOME_RULE[r.outcome])}>
            <h3 className="pt-3 text-md font-bold">{r.product_name}</h3>
            <p className="figures text-sm text-muted">{r.product_id}</p>
            <dl className="mt-3">
              {rows.map((row) => (
                <div key={row.key} className="flex flex-col gap-1.5 border-t border-line py-3">
                  <dt className="font-bold">{row.header}</dt>
                  <dd>{row.spanning ?? row.cell(r, i)}</dd>
                </div>
              ))}
            </dl>
            <div className="border-t-2 border-ink pt-4">{renderAction(r)}</div>
          </li>
        ))}
      </ol>
    </>
  );
}
