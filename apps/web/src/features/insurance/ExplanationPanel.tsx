import { Info } from "lucide-react";
import { Provenance } from "../../components/Provenance";
import type { Explanation, Recommendation } from "../finance/api";

/** The plain-language explanation of the outcomes, with where it came from. */
export function ExplanationPanel({ explanation, results }: { explanation: Explanation; results: readonly Recommendation[] }) {
  const live = explanation.source === "live";
  const nameOf = (productId: string) => results.find((r) => r.product_id === productId)?.product_name ?? productId;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Provenance source={live ? "live" : "simulated"} />
        <span className="font-bold">{live ? "Explained by the language model from the terms above" : "Template explanation (offline)"}</span>
        {live && explanation.model && <span className="figures text-sm text-muted">{explanation.model}</span>}
      </div>
      <p className="max-w-[70ch] text-md">{explanation.summary}</p>
      {explanation.items.length > 0 && (
        <dl className="grid max-w-[110ch] gap-x-8 lg:grid-cols-3">
          {explanation.items.map((item) => (
            <div key={item.product_id} className="flex flex-col gap-1 border-t border-line py-3">
              <dt className="font-bold">{nameOf(item.product_id)}</dt>
              <dd className="flex flex-col gap-1">
                <p>{item.explanation}</p>
                {item.terms_refs.length > 0 && (
                  <p className="text-sm text-muted">
                    Cites <span className="figures">{item.terms_refs.join(", ")}</span>
                  </p>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {explanation.grounding_dropped && (
        <p className="flex max-w-[70ch] gap-2 rounded-control border-2 border-uncertain bg-uncertain-soft p-3">
          <Info aria-hidden="true" className="mt-0.5 size-5 flex-none text-uncertain-ink" strokeWidth={2.25} />
          Some sentences were removed because they did not cite a term on this page. What remains is grounded in the terms
          above.
        </p>
      )}
      {explanation.caveats.length > 0 && (
        <ul className="flex max-w-[70ch] list-disc flex-col gap-1 pl-5 text-muted">
          {explanation.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
