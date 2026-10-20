import { Calculator, Lock } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/feedback";
import { Money, Mono, Range, Timestamp } from "../../components/figures";
import { Section } from "../../components/layout";
import { Provenance } from "../../components/Provenance";
import { useToast } from "../../components/Toast";
import { asSource } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { formatMoney } from "../../lib/format";
import { useRole } from "../../lib/role-store";
import { useConfirmValuation, type EstimateOut, type Passport, type ValuationOut } from "./api";
import { parseKg, parsePriceMinor, valueRange } from "./valuation";

export const DEFAULT_PRICE = "5.20";
export const DEFAULT_PRICE_SOURCE = "Demo reference price (fictional)";
export const DEFAULT_PRICE_DATE = "2026-10-01";

const INPUT =
  "min-h-11 w-full rounded-control border-2 border-line-strong bg-bg px-3 py-2 figures placeholder:text-muted hover:border-ink focus:border-ink aria-invalid:border-danger";

function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-bold">
        {label}
      </label>
      {children}
      {hint && <span className="text-sm text-muted">{hint}</span>}
    </div>
  );
}

function ValuationLine({ valuation, weightSource }: { valuation: ValuationOut; weightSource?: string }) {
  const price = formatMoney(valuation.unit_price_minor_per_kg, valuation.currency, { bare: true });
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-md">
      <Range low={valuation.weight_low_kg} high={valuation.weight_high_kg} unit="kg" className="font-bold" />
      <span aria-hidden="true">×</span>
      <span className="sr-only">times</span>
      <Mono className="font-bold">
        {price} {valuation.currency}/kg
      </Mono>
      <span aria-hidden="true">=</span>
      <span className="sr-only">equals</span>
      <Money low={valuation.value_low_minor} high={valuation.value_high_minor} currency={valuation.currency} exact className="font-bold" />
      {valuation.weight_basis === "estimate" && weightSource && <Provenance source={asSource(weightSource)} />}
    </p>
  );
}

export function ValuationSection({ passport }: { passport: Passport }) {
  const role = useRole();
  const toast = useToast();
  const ids = { basis: useId(), estimate: useId(), low: useId(), high: useId(), price: useId(), source: useId(), date: useId(), result: useId() };
  const weights = passport.estimates.filter((estimate) => estimate.kind === "weight" && estimate.range_low != null && estimate.range_high != null);
  const sorted = [...passport.valuations].sort((a, b) => b.version - a.version);
  const current = sorted[0];
  const weightEstimate = (id: string | null | undefined): EstimateOut | undefined => passport.estimates.find((e) => e.id === id);
  const canValue = role.role === "manager" || role.role === "operator";
  const confirm = useConfirmValuation(passport.animal.id);

  const [basis, setBasis] = useState<"estimate" | "override">(weights.length ? "estimate" : "override");
  const [estimateId, setEstimateId] = useState(weights[0]?.id ?? "");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [price, setPrice] = useState(DEFAULT_PRICE);
  const [source, setSource] = useState(DEFAULT_PRICE_SOURCE);
  const [date, setDate] = useState(DEFAULT_PRICE_DATE);

  const chosen = weights.find((w) => w.id === estimateId);
  const lowKg = basis === "estimate" ? (chosen?.range_low ?? null) : parseKg(low);
  const highKg = basis === "estimate" ? (chosen?.range_high ?? null) : parseKg(high);
  const priceMinor = parsePriceMinor(price);
  const rangeValid = lowKg != null && highKg != null && lowKg <= highKg;
  const preview = rangeValid && priceMinor ? valueRange(lowKg, highKg, priceMinor) : null;
  const ready = Boolean(preview && source.trim() && date);

  const submit = async () => {
    if (!ready || !priceMinor) return;
    try {
      const result = await confirm.mutateAsync({
        weight_basis: basis,
        estimate_id: basis === "estimate" ? estimateId : null,
        weight_low_kg: basis === "override" ? lowKg : null,
        weight_high_kg: basis === "override" ? highKg : null,
        unit_price_minor_per_kg: priceMinor,
        price_source: source.trim(),
        price_date: date,
      });
      toast.show({
        title: `Valued · version ${result.version}`,
        body: `${formatMoney(result.value_low_minor, result.currency, { whole: true })}–${formatMoney(result.value_high_minor, result.currency, { whole: true })}, posted to the passbook.`,
        tone: "ok",
      });
    } catch {
      // Shown below the form.
    }
  };

  return (
    <Section
      anchor="valuation"
      title="Indicative valuation"
      description="An indicative range, not a market appraisal: the weight range times a reference price per kilogram."
    >
      {current ? (
        <div className="flex flex-col gap-3">
          <ValuationLine valuation={current} weightSource={weightEstimate(current.estimate_id)?.source} />
          <p className="text-muted">
            Version <Mono className="text-ink">{current.version}</Mono> · {current.price_source} · price date{" "}
            <Mono className="text-ink">{current.price_date}</Mono> · weight {current.weight_basis === "override" ? "entered by hand" : "from the estimate"} ·
            confirmed by {current.confirmed_by}
          </p>
        </div>
      ) : (
        <p className="rounded-control border-2 border-dashed border-line-strong p-4 text-muted">
          No valuation yet. Confirm one below to give this animal an indicative exposure.
        </p>
      )}

      {sorted.length > 1 && (
        <details className="mt-4">
          <summary className="min-h-11 cursor-pointer py-2 font-bold">Version history · {sorted.length} versions</summary>
          <ol className="flex flex-col border-t border-line">
            {sorted.map((valuation) => (
              <li key={valuation.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line py-3">
                <span>
                  <Mono className="font-bold">v{valuation.version}</Mono>{" "}
                  <Money low={valuation.value_low_minor} high={valuation.value_high_minor} currency={valuation.currency} />
                </span>
                <span className="text-sm text-muted">
                  <Range low={valuation.weight_low_kg} high={valuation.weight_high_kg} unit="kg" /> · {valuation.weight_basis} ·{" "}
                  <Timestamp value={valuation.created_at} mode="absolute" />
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}

      <div className="mt-6 rounded-panel border-2 border-ink p-5">
        <h3 className="flex items-center gap-2 text-md font-bold">
          <Calculator aria-hidden="true" className="size-5" strokeWidth={2.25} />
          Confirm a new valuation
        </h3>
        {!canValue ? (
          <p className="mt-3 flex items-center gap-2 text-muted">
            <Lock aria-hidden="true" className="size-4 flex-none" strokeWidth={2.25} />
            Only a manager or operator can confirm a valuation.
          </p>
        ) : (
          <form
            className="mt-4 flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-bold">Weight basis</legend>
              <div className="flex flex-wrap gap-2">
                {(["estimate", "override"] as const).map((option) => (
                  <label
                    key={option}
                    className={cn(
                      "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control border-2 px-4 font-bold",
                      basis === option ? "border-ink bg-ink text-white" : "border-ink bg-bg hover:bg-surface-2",
                      option === "estimate" && weights.length === 0 && "cursor-not-allowed border-line text-muted",
                    )}
                  >
                    <input
                      type="radio"
                      name={ids.basis}
                      value={option}
                      checked={basis === option}
                      disabled={option === "estimate" && weights.length === 0}
                      onChange={() => setBasis(option)}
                      className="size-4 accent-current"
                    />
                    {option === "estimate" ? "Use the weight estimate" : "Enter a weight range"}
                  </label>
                ))}
              </div>
            </fieldset>

            {basis === "estimate" ? (
              <Field label="Weight estimate" htmlFor={ids.estimate}>
                <select id={ids.estimate} value={estimateId} onChange={(event) => setEstimateId(event.target.value)} className={INPUT}>
                  {weights.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.range_low}–{w.range_high} {w.unit} · {w.method_version} · {w.source}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                <Field label="Low (kg)" htmlFor={ids.low}>
                  <input id={ids.low} inputMode="decimal" value={low} onChange={(e) => setLow(e.target.value)} className={INPUT} aria-invalid={low !== "" && parseKg(low) == null} />
                </Field>
                <Field label="High (kg)" htmlFor={ids.high}>
                  <input id={ids.high} inputMode="decimal" value={high} onChange={(e) => setHigh(e.target.value)} className={INPUT} aria-invalid={high !== "" && (parseKg(high) == null || !rangeValid)} />
                </Field>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)]">
              <Field label="Price (USD/kg)" htmlFor={ids.price}>
                <input id={ids.price} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} className={INPUT} aria-invalid={!priceMinor} />
              </Field>
              <Field label="Price source" htmlFor={ids.source}>
                <input id={ids.source} value={source} onChange={(e) => setSource(e.target.value)} className={cn(INPUT, "font-sans")} aria-invalid={!source.trim()} />
              </Field>
              <Field label="Price date" htmlFor={ids.date}>
                <input id={ids.date} type="date" value={date} onChange={(e) => setDate(e.target.value)} className={INPUT} aria-invalid={!date} />
              </Field>
            </div>

            <output id={ids.result} htmlFor={`${ids.low} ${ids.high} ${ids.price}`} aria-live="polite" className="flex flex-wrap items-baseline justify-between gap-2 border-y-2 border-ink py-3">
              <span>Indicative value</span>
              {preview ? (
                <Money low={preview.low} high={preview.high} currency="USD" exact className="text-md font-bold" />
              ) : (
                <span className="text-muted">
                  {basis === "override" && lowKg != null && highKg != null && lowKg > highKg
                    ? "The low weight must not exceed the high weight."
                    : "Enter a weight range and a price to see it."}
                </span>
              )}
            </output>

            {confirm.error ? <ErrorNotice error={confirm.error} /> : null}

            <div>
              <Button type="submit" variant="primary" disabled={!ready} loading={confirm.isPending} loadingLabel="Confirming…">
                Confirm valuation
              </Button>
            </div>
          </form>
        )}
      </div>
    </Section>
  );
}
