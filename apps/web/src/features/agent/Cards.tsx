import { CircleCheck, CircleDashed, CircleX, Hourglass, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Money, Mono } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { cn } from "../../lib/cn";
import { ActionReview } from "../actions/ActionReview";
import type { AgentAction } from "../actions/types";
import { EvidenceChecklist } from "../claims/EvidenceChecklist";
import type { ChecklistItem, Recommendation } from "../finance/api";
import { ComparisonTable } from "../insurance/ComparisonTable";
import { perilLabel } from "../insurance/comparison";
import type { AgentCard } from "./api";

/* Card data is built by the backend from records (domain/agent_chat.py); these are its shapes. */
type Data = Record<string, unknown>;
interface Cited {
  text: string;
  terms_ref: string | null;
}
interface Step {
  key: string;
  label: string;
  state: "done" | "current" | "waiting" | "failed";
  detail: string | null;
}
interface Fix {
  key: string;
  label: string;
  fix: string;
  href: string | null;
}
interface TimelineEntry {
  status: string;
  label: string;
  note: string | null;
  settlement_minor: number | null;
  disbursement: string | null;
  at: string | null;
}

function Frame({ title, children, aside, className }: { title: string; children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <section className={cn("flex flex-col gap-3 rounded-panel border-2 border-ink bg-bg p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Ref({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  return <span className="figures text-sm whitespace-nowrap text-muted">{value}</span>;
}

function CitedList({ items }: { items: Cited[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.text} className="flex gap-2">
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 flex-none text-ok" strokeWidth={2.25} />
          <span>
            {item.text} <Ref value={item.terms_ref} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function PassportSummary({ data }: { data: Data }) {
  const coverage = data.coverage as { status: string; label: string; product_name: string | null };
  const valuation = data.valuation as { value_low_minor: number; value_high_minor: number; currency: string; version: number } | null;
  const tone: StatusTone = coverage.status === "active" ? "ok" : coverage.status === "pending" ? "awaiting" : "danger";
  return (
    <Frame title="Passport" aside={<StatusPill tone={tone} label={coverage.label} />}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        <dt className="text-muted">Identity</dt>
        <dd>{data.identity_status === "confirmed" ? "Confirmed" : String(data.identity_status)}</dd>
        <dt className="text-muted">Value</dt>
        <dd>
          {valuation ? (
            <span className="flex flex-wrap items-center gap-2">
              <span>
                <Money minor={valuation.value_low_minor} currency={valuation.currency} /> –{" "}
                <Money minor={valuation.value_high_minor} currency={valuation.currency} />
              </span>
              <span className="text-sm text-muted">estimate, v{valuation.version}</span>
            </span>
          ) : (
            <span className="text-muted">Not confirmed</span>
          )}
        </dd>
        {coverage.product_name && (
          <>
            <dt className="text-muted">Plan</dt>
            <dd>{coverage.product_name}</dd>
          </>
        )}
      </dl>
      <Link to={String(data.passport_href)} className="self-start font-bold">
        Open the passport
      </Link>
    </Frame>
  );
}

function Questions({ data }: { data: Data }) {
  const questions = data.questions as { id: string; text: string; why: string; terms_ref: string; answer: string | null }[];
  return (
    <Frame title={questions.length === 1 ? "One question" : `${questions.length} questions`}>
      <ol className="flex flex-col gap-2">
        {questions.map((q) => (
          <li key={q.id} className={cn("flex flex-col", q.id === data.current && "font-bold")}>
            <span>{q.text}</span>
            <span className="text-sm font-regular text-muted">
              {q.answer ? `Answered: ${q.answer}` : q.why} <Ref value={q.terms_ref} />
            </span>
          </li>
        ))}
      </ol>
    </Frame>
  );
}

function PlanComparison({ data }: { data: Data }) {
  const results = data.results as Recommendation[];
  return (
    <Frame title={`${results.length} sample plans · ${String(data.provider)}`} aside={<Provenance source="simulated" />}>
      <p className="text-sm text-muted">
        Insured value <Money minor={data.insured_value_minor as number} currency={String(data.currency)} /> · {String(data.note)}
      </p>
      <ComparisonTable results={results} renderAction={() => null} />
    </Frame>
  );
}

function RecommendationCard({ data }: { data: Data }) {
  const currency = String(data.currency);
  return (
    <Frame title={`Recommended: ${String(data.product_name)}`} aside={<StatusPill tone="ok" label="Eligible" />}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        <dt className="text-muted">Premium a year</dt>
        <dd>
          <Money minor={data.premium_minor as number} currency={currency} className="font-bold" />
        </dd>
        <dt className="text-muted">Cover up to</dt>
        <dd>
          <Money minor={data.insured_value_minor as number} currency={currency} />
        </dd>
        <dt className="text-muted">Deductible</dt>
        <dd>
          <Money minor={data.deductible_minor as number} currency={currency} />
        </dd>
        <dt className="text-muted">Covers</dt>
        <dd>{(data.covered_perils as string[]).map(perilLabel).join(", ")}</dd>
      </dl>
      <h4 className="font-bold">Why</h4>
      <CitedList items={data.reasons as Cited[]} />
      {(data.tradeoffs as Cited[]).length > 0 && (
        <>
          <h4 className="font-bold">Trade-off</h4>
          <ul className="flex flex-col gap-2">
            {(data.tradeoffs as Cited[]).map((t) => (
              <li key={t.text}>
                {t.text} <Ref value={t.terms_ref} />
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="text-sm text-muted">{String(data.rule)}</p>
    </Frame>
  );
}

function ApplicationDraft({ data }: { data: Data }) {
  const fields = data.fields as { label: string; value: string; source: string }[];
  const evidence = data.evidence as { type: string; ref: string; label: string }[];
  return (
    <Frame title={`Application to ${String(data.recipient)}`} aside={<StatusPill tone="awaiting" label="Filled, not sent" />}>
      <dl className="flex flex-col">
        {fields.map((f) => (
          <div key={f.label} className="flex flex-wrap items-baseline justify-between gap-x-3 border-b border-line py-2">
            <dt className="text-muted">{f.label}</dt>
            <dd className="text-right">
              <span className="font-bold">{f.value}</span>
              <span className="block text-sm text-muted">{f.source}</span>
            </dd>
          </div>
        ))}
      </dl>
      <h4 className="font-bold">
        Evidence attached · <Mono>{evidence.length}</Mono>
      </h4>
      <ul className="flex flex-col gap-1">
        {evidence.map((item) => (
          <li key={`${item.type}-${item.ref}`} className="flex gap-2">
            <CircleCheck aria-hidden="true" className="mt-0.5 size-5 flex-none text-ok" strokeWidth={2.25} />
            <span>{item.label}</span>
          </li>
        ))}
      </ul>
    </Frame>
  );
}

const STEP: Record<Step["state"], { icon: LucideIcon; word: string; className: string }> = {
  done: { icon: CircleCheck, word: "Done", className: "text-ok" },
  current: { icon: Hourglass, word: "Waiting", className: "text-await-ink" },
  waiting: { icon: CircleDashed, word: "Not yet", className: "text-muted" },
  failed: { icon: CircleX, word: "Failed", className: "text-danger" },
};

function StatusSteps({ data }: { data: Data }) {
  const steps = data.steps as Step[];
  return (
    <Frame title="Where the cover stands" aside={<Provenance source="simulated" />}>
      <ol className="flex flex-col">
        {steps.map((step, index) => {
          const s = STEP[step.state];
          const Icon = s.icon;
          return (
            <li
              key={step.key}
              className={cn(
                "flex gap-3 py-3",
                index > 0 && "border-t border-line",
                step.state === "current" && "rounded-control border-2 border-tag-edge bg-tag-soft px-3",
              )}
            >
              <Icon aria-hidden="true" className={cn("mt-0.5 size-6 flex-none", s.className)} strokeWidth={2.25} />
              <div className="min-w-0">
                <p className="font-bold">
                  {step.label} <span className={cn("text-sm", s.className)}>· {s.word}</span>
                </p>
                {step.detail && <p className="text-sm break-words text-muted">{step.detail}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </Frame>
  );
}

function ClaimChecklistCard({ data }: { data: Data }) {
  const items = (data.items as ChecklistItem[]).filter((i) => (i.status as string) !== "required");
  const required = (data.items as { key: string; label: string; status: string }[]).filter((i) => i.status === "required");
  if (required.length > 0) {
    return (
      <Frame title="What a claim needs">
        <ul className="flex flex-col gap-1">
          {required.map((r) => (
            <li key={r.key} className="flex gap-2">
              <CircleDashed aria-hidden="true" className="mt-0.5 size-5 flex-none text-muted" strokeWidth={2.25} />
              {r.label}
            </li>
          ))}
        </ul>
      </Frame>
    );
  }
  return (
    <Frame
      title="Claim checklist"
      aside={
        data.claim_id ? (
          <Link to={`/claims/${String(data.claim_id)}`} className="figures text-sm">
            {String(data.claim_id)}
          </Link>
        ) : null
      }
    >
      {data.claimed_amount_minor != null && (
        <p>
          Claimed <Money minor={data.claimed_amount_minor as number} currency={String(data.currency)} className="font-bold" />{" "}
          <span className="text-sm text-muted">(the farm's estimate; the insurer assesses)</span>
        </p>
      )}
      <EvidenceChecklist items={items} />
    </Frame>
  );
}

function MissingItems({ data }: { data: Data }) {
  const items = data.items as Fix[];
  return (
    <Frame title="What's missing and how to fix it">
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.key} className="flex flex-col gap-1 rounded-control border-2 border-dashed border-line-strong p-3">
            <span className="font-bold">{item.label}</span>
            <span>{item.fix}</span>
            {item.href && (
              <Link to={item.href} className="self-start font-bold">
                Go there
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Frame>
  );
}

function Receipt({ data }: { data: Data }) {
  return (
    <Frame title={String(data.title)} aside={<Provenance source="simulated" />}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        <dt className="text-muted">From</dt>
        <dd>{String(data.provider)} (sandbox)</dd>
        <dt className="text-muted">Reference</dt>
        <dd>
          <Mono>{String(data.reference ?? "—")}</Mono>
        </dd>
        {data.effective_date != null && (
          <>
            <dt className="text-muted">Cover</dt>
            <dd>
              <Mono>
                {String(data.effective_date)} to {String(data.expiry_date)}
              </Mono>
            </dd>
          </>
        )}
        {data.claimed_amount_minor != null && (
          <>
            <dt className="text-muted">Claimed</dt>
            <dd>
              <Money minor={data.claimed_amount_minor as number} currency={String(data.currency)} />
            </dd>
          </>
        )}
      </dl>
    </Frame>
  );
}

function ClaimStatus({ data }: { data: Data }) {
  const timeline = data.timeline as TimelineEntry[];
  const settlement = data.settlement as { amount_minor: number | null; disbursement: string | null } | null;
  return (
    <Frame title="Claim status · insurer reported" aside={<StatusPill tone={data.status === "declined" ? "danger" : data.status === "approved" ? "ok" : "awaiting"} label={String(data.label)} />}>
      <ol className="flex flex-col">
        {timeline.map((entry, index) => (
          <li key={`${entry.status}-${index}`} className={cn("flex flex-col py-2", index > 0 && "border-t border-line")}>
            <span className="font-bold">{entry.label}</span>
            <span className="text-sm text-muted">
              {entry.at && <Mono>{entry.at.replace("T", " ").slice(0, 16)}</Mono>} {entry.note}
            </span>
          </li>
        ))}
      </ol>
      {settlement && (
        <p>
          Settlement stated by the insurer:{" "}
          {settlement.amount_minor != null ? <Money minor={settlement.amount_minor} currency={String(data.currency)} className="font-bold" /> : "not stated"}
          . Disbursement: {settlement.disbursement === "paid" ? "paid, as reported by the insurer" : "scheduled by the insurer"}.
        </p>
      )}
    </Frame>
  );
}

export function CardView({ card, onSettled }: { card: AgentCard; onSettled: (action: AgentAction) => void }) {
  const data = card.data as Data;
  switch (card.type) {
    case "passport_summary":
      return <PassportSummary data={data} />;
    case "eligibility_questions":
      return <Questions data={data} />;
    case "plan_comparison":
      return <PlanComparison data={data} />;
    case "recommendation":
      return <RecommendationCard data={data} />;
    case "application_draft":
      return <ApplicationDraft data={data} />;
    case "action_review":
      return (
        <section className="rounded-panel border-2 border-tag-edge bg-bg p-4">
          <ActionReview actionId={String(data.action_id)} onSettled={onSettled} />
        </section>
      );
    case "status_steps":
      return <StatusSteps data={data} />;
    case "claim_checklist":
      return <ClaimChecklistCard data={data} />;
    case "missing_items":
      return <MissingItems data={data} />;
    case "receipt":
      return <Receipt data={data} />;
    case "claim_status":
      return <ClaimStatus data={data} />;
    default:
      return null;
  }
}
