import { ArrowRight, TriangleAlert } from "lucide-react";
import { Link } from "react-router";
import { Timestamp } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { answerAnimal, factLink, factText, isInstant, missingCallout, type AssistantAnswer } from "./answer";

/**
 * One answer. The text and every fact come from the farm's records (the server builds them); the model, when
 * live, only parsed the question. Missing evidence is stated, never smoothed over.
 */
export function AnswerCard({ answer }: { answer: AssistantAnswer }) {
  const animal = answerAnimal(answer);
  // A gap the answer already states shows as its recovery instead of the same sentence twice.
  const callouts = answer.missing.flatMap((code) => {
    const callout = missingCallout(answer.answer, code, animal);
    return callout ? [{ code, callout }] : [];
  });
  return (
    <div className="flex flex-col gap-4">
      <p className="text-md">{answer.answer}</p>

      {callouts.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="Missing evidence">
          {callouts.map(({ code, callout }) => (
            <li key={code} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-control border-2 border-uncertain bg-uncertain-soft px-3 py-2.5">
              <TriangleAlert aria-hidden="true" className="size-5 flex-none text-uncertain-ink" strokeWidth={2.25} />
              <span className="min-w-0 flex-1 font-bold text-uncertain-ink">{callout.text}</span>
              {callout.link && (
                <Link
                  to={callout.link.to}
                  className="inline-flex min-h-11 items-center gap-1 rounded-control px-2 text-sm font-bold whitespace-nowrap text-ink hover:bg-bg"
                >
                  {callout.link.label}
                  <ArrowRight aria-hidden="true" className="size-4" strokeWidth={2.5} />
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {answer.facts.length > 0 && (
        <dl className="flex flex-col border-t border-line">
          {answer.facts.map((fact, i) => {
            // One link per run of facts from the same record, not "Open passport" on every row.
            const link = factLink(fact, animal?.id ?? null);
            const previous = i > 0 ? factLink(answer.facts[i - 1]!, animal?.id ?? null) : null;
            const repeated = link !== null && previous !== null && previous.to === link.to;
            return (
              <div key={`${fact.record_type}-${fact.record_id}-${i}`} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 border-b border-line py-2.5">
                <dt className="text-sm text-muted">{fact.label}</dt>
                <dd className="col-start-1 min-w-0 font-bold break-words">
                  {isInstant(fact.value) ? <Timestamp value={fact.value} /> : factText(fact.value)}
                </dd>
                {link && !repeated && (
                  <dd className="col-start-2 row-span-2 row-start-1">
                    <Link
                      to={link.to}
                      className="inline-flex min-h-11 items-center gap-1 rounded-control px-2 text-sm font-bold whitespace-nowrap hover:bg-surface-2"
                    >
                      {link.label}
                      <ArrowRight aria-hidden="true" className="size-4" strokeWidth={2.5} />
                    </Link>
                  </dd>
                )}
              </div>
            );
          })}
        </dl>
      )}

      <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
        {answer.parsed_by === "live" ? (
          <>
            <Provenance source="live" /> Claude parsed this question; the answer comes from the farm's records.
          </>
        ) : (
          <>
            <Provenance source="simulated" /> Parsed offline; the answer comes from the farm's records.
          </>
        )}
      </p>
    </div>
  );
}
