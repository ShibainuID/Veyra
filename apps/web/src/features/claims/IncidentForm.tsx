import { FilePlus2, FlaskConical } from "lucide-react";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/feedback";
import { Mono } from "../../components/figures";
import { useToast } from "../../components/Toast";
import { alertKindLabel } from "../../lib/animal";
import { cn } from "../../lib/cn";
import { formatAbsolute, formatMoney } from "../../lib/format";
import { parseMoneyInput } from "../../lib/money-input";
import { toApiError } from "../../lib/errors";
import { formatDate } from "../finance/dates";
import { useAlerts, usePolicies, type AnimalRow } from "../finance/api";
import { perilLabel } from "../insurance/comparison";
import { useCatalog, useRecordIncident } from "./api";
import { INCIDENT_KINDS, type IncidentKind } from "./labels";

/** The demo's sample incident for Sari (demo/fixtures/incidents.json, demo-incident-001). */
const DEMO_INCIDENT = {
  animalId: "animal-demo-001",
  kind: "accidental_injury" as IncidentKind,
  description: "Left hind lameness found at the morning check after a reduced-movement alert. Animal is standing and eating.",
  loss: "600.00",
  location: "Pen A",
  foundBy: "A. Pratama",
};

export const FIELD =
  "min-h-11 w-full rounded-control border-2 border-line-strong bg-bg px-3 py-2 text-base placeholder:text-muted focus:border-ink disabled:bg-surface disabled:text-muted";

function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function Field({ label, hint, error, htmlFor, children }: { label: ReactNode; hint?: ReactNode; error?: string | null; htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="font-bold">
        {label}
      </label>
      {hint && <p className="text-sm text-muted">{hint}</p>}
      {children}
      {error && (
        <p className="text-sm font-bold text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export interface IncidentFormProps {
  animals: readonly AnimalRow[];
  initialAnimalId?: string;
  initialAlertId?: string;
  onDone: () => void;
}

/** Why an animal can't be claimed against, or null when it can. */
export function claimBlock(animal: AnimalRow): string | null {
  if (animal.identity_status !== "confirmed") return "identity not confirmed";
  if (animal.coverage.status !== "active") return animal.coverage.status === "pending" ? "cover not active yet" : "no active cover";
  return null;
}

/**
 * Records what happened, in the farm's words, then drafts the claim. Only animals with active
 * cover can be chosen; the others are listed, disabled, with the reason.
 */
export function IncidentForm({ animals, initialAnimalId, initialAlertId, onDone }: IncidentFormProps) {
  const ids = { animal: useId(), kind: useId(), when: useId(), description: useId(), loss: useId(), location: useId(), foundBy: useId() };
  const navigate = useNavigate();
  const toast = useToast();
  const record = useRecordIncident();
  const catalog = useCatalog();
  const claimable = animals.filter((a) => claimBlock(a) === null);
  const [animalId, setAnimalId] = useState(() =>
    initialAnimalId && claimable.some((a) => a.id === initialAnimalId) ? initialAnimalId : (claimable[0]?.id ?? ""),
  );
  const [kind, setKind] = useState<IncidentKind>("accidental_injury");
  const [occurredAt, setOccurredAt] = useState(() => toLocalInput(new Date()));
  const [description, setDescription] = useState("");
  const [loss, setLoss] = useState("");
  const [location, setLocation] = useState("");
  const [foundBy, setFoundBy] = useState("");
  const [linked, setLinked] = useState<string[]>(initialAlertId ? [initialAlertId] : []);
  const [submitted, setSubmitted] = useState(false);

  const animal = animals.find((a) => a.id === animalId);
  const alerts = useAlerts(animalId || undefined, Boolean(animalId));
  const product = useMemo(
    () => catalog.data?.products?.find((p) => p.product_id === animal?.coverage.product_id),
    [catalog.data, animal?.coverage.product_id],
  );
  const policies = usePolicies(animalId || undefined);
  const activePolicy = policies.data?.find((p) => p.status === "active" && p.id === animal?.coverage.policy_id);
  const occurredDay = occurredAt && !Number.isNaN(new Date(occurredAt).getTime()) ? new Date(occurredAt).toISOString().slice(0, 10) : null;
  const outsideCover =
    activePolicy && occurredDay
      ? (activePolicy.effective_date !== null && occurredDay < activePolicy.effective_date) ||
        (activePolicy.expiry_date !== null && occurredDay > activePolicy.expiry_date)
      : false;
  const kindCovered = !product || product.covered_perils.includes(kind);
  const lossMinor = parseMoneyInput(loss);
  const errors = {
    animal: animalId ? null : "Choose an animal with active cover.",
    when:
      !occurredAt || new Date(occurredAt).getTime() > Date.now() + 60_000
        ? "Enter when it happened (not in the future)."
        : outsideCover && activePolicy
          ? `This incident happened outside the policy's cover period (${formatDate(activePolicy.effective_date)} – ${formatDate(activePolicy.expiry_date)}), so no claim can be drafted.`
          : null,
    description: description.trim().length >= 5 ? null : "Describe what happened in a few words.",
    loss: lossMinor !== null && lossMinor > 0 ? null : "Enter the estimated loss in USD, for example 1,200.00.",
    kind: kindCovered ? null : `${product?.name ?? "This policy"} doesn't cover ${perilLabel(kind).toLowerCase()}, so no claim can be drafted.`,
  };
  const valid = Object.values(errors).every((e) => e === null);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (!valid || lossMinor === null) return;
    const facts: Record<string, string> = {};
    if (location.trim()) facts.location = location.trim();
    if (foundBy.trim()) facts.found_by = foundBy.trim();
    record.mutate(
      {
        animal_id: animalId,
        kind,
        occurred_at: new Date(occurredAt).toISOString(),
        description: description.trim(),
        estimated_loss_minor: lossMinor,
        linked_alert_ids: linked.filter((id) => alerts.data?.some((a) => a.id === id)),
        facts,
      },
      {
        onSuccess: ({ claim }) => {
          if (!claim) return;
          toast.show({ tone: "ok", title: "Incident recorded and claim drafted", body: "Check the evidence list before preparing the submission." });
          onDone();
          navigate(`/claims/${claim.id}`);
        },
      },
    );
  };

  const show = (key: keyof typeof errors) => (submitted ? errors[key] : null);

  return (
    <form id="incident-form" noValidate onSubmit={onSubmit} className="flex flex-col gap-6">
      {animalId === DEMO_INCIDENT.animalId && !description && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border-2 border-dashed border-line-strong px-4 py-3">
          <p className="text-sm text-muted">Demo: fill the form with the prepared sample incident for Sari.</p>
          <Button
            type="button"
            variant="secondary"
            icon={FlaskConical}
            onClick={() => {
              setKind(DEMO_INCIDENT.kind);
              setDescription(DEMO_INCIDENT.description);
              setLoss(DEMO_INCIDENT.loss);
              setLocation(DEMO_INCIDENT.location);
              setFoundBy(DEMO_INCIDENT.foundBy);
            }}
          >
            Use the sample incident
          </Button>
        </div>
      )}
      <Field label="Animal" htmlFor={ids.animal} hint="Only animals with active cover can be claimed against." error={show("animal")}>
        <select id={ids.animal} className={FIELD} value={animalId} onChange={(e) => setAnimalId(e.target.value)}>
          {claimable.length === 0 && <option value="">No animal has active cover</option>}
          {animals.map((a) => {
            const block = claimBlock(a);
            return (
              <option key={a.id} value={a.id} disabled={block !== null}>
                {a.name} · {a.id}
                {block ? ` — ${block}` : ""}
              </option>
            );
          })}
        </select>
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 font-bold">What happened</legend>
        {product && (
          <p className="text-sm text-muted">
            {product.name} covers {product.covered_perils.map((p) => perilLabel(p).toLowerCase()).join(" and ")}.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2">
          {INCIDENT_KINDS.map((k) => {
            const covered = !product || product.covered_perils.includes(k.value);
            return (
              <label
                key={k.value}
                className={cn(
                  "flex min-h-11 cursor-pointer items-center gap-2 rounded-control border-2 px-3 font-bold",
                  kind === k.value ? "border-ink bg-surface-2" : "border-line-strong",
                )}
              >
                <input type="radio" name="kind" value={k.value} checked={kind === k.value} onChange={() => setKind(k.value)} className="size-5 accent-[var(--ink)]" />
                <span>{k.label}</span>
                {!covered && <span className="ml-auto text-sm font-regular text-muted">not covered</span>}
              </label>
            );
          })}
        </div>
        {errors.kind && (
          <p className="text-sm font-bold text-danger" role="alert">
            {errors.kind}
          </p>
        )}
      </fieldset>

      <Field label="When it happened" htmlFor={ids.when} hint="Local time on this device." error={outsideCover ? errors.when : show("when")}>
        <input id={ids.when} type="datetime-local" className={FIELD} value={occurredAt} max={toLocalInput(new Date())} onChange={(e) => setOccurredAt(e.target.value)} />
      </Field>

      <Field label="Description" htmlFor={ids.description} hint="What the farm saw, in plain words. This is the farmer's report." error={show("description")}>
        <textarea id={ids.description} rows={3} className={FIELD} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Found lame at the morning check, with a cut on the left hind leg." />
      </Field>

      <Field
        label="Estimated loss"
        htmlFor={ids.loss}
        hint={lossMinor !== null && lossMinor > 0 ? <>Recorded as <Mono>{formatMoney(lossMinor, "USD")}</Mono></> : "In USD, the farm's own estimate."}
        error={show("loss")}
      >
        <div className="flex items-stretch">
          <input
            id={ids.loss}
            inputMode="decimal"
            autoComplete="off"
            className={cn(FIELD, "figures rounded-r-none")}
            value={loss}
            onChange={(e) => setLoss(e.target.value)}
            placeholder="1,200.00"
          />
          <span className="figures flex items-center rounded-r-control border-2 border-l-0 border-line-strong bg-surface-2 px-3 font-bold">USD</span>
        </div>
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 font-bold">Linked camera alerts</legend>
        <p className="text-sm text-muted">Observations from the cameras, kept separate from the farm's report.</p>
        {alerts.data && alerts.data.length > 0 ? (
          alerts.data.map((alert) => (
            <label key={alert.id} className="flex min-h-11 cursor-pointer items-start gap-3 rounded-control border-2 border-line-strong p-3">
              <input
                type="checkbox"
                className="mt-0.5 size-5 flex-none accent-[var(--ink)]"
                checked={linked.includes(alert.id)}
                onChange={(e) => setLinked((all) => (e.target.checked ? [...all, alert.id] : all.filter((id) => id !== alert.id)))}
              />
              <span className="flex flex-col">
                <span className="font-bold">
                  {alertKindLabel(alert.kind)} · {alert.camera_name}
                </span>
                <span className="figures text-sm text-muted">
                  {alert.id} · {formatAbsolute(alert.window_start)}
                </span>
              </span>
            </label>
          ))
        ) : (
          <p className="rounded-control border-2 border-dashed border-line-strong p-3 text-sm text-muted">
            {alerts.isPending && animalId ? "Loading alerts…" : "No camera alerts for this animal."}
          </p>
        )}
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1.5 font-bold">Further facts (optional)</legend>
        <Field label="Where it happened" htmlFor={ids.location}>
          <input id={ids.location} className={FIELD} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Pen A, by the feed line" />
        </Field>
        <Field label="Found by" htmlFor={ids.foundBy}>
          <input id={ids.foundBy} className={FIELD} value={foundBy} onChange={(e) => setFoundBy(e.target.value)} placeholder="Name of the person who found it" />
        </Field>
      </fieldset>

      {record.error ? <ErrorNotice error={record.error} title="The incident wasn't recorded" /> : null}
      {record.data?.draftError ? (
        <div className="flex flex-col gap-2">
          <ErrorNotice error={record.data.draftError} title={`Incident ${record.data.incident.id} is recorded, but no claim could be drafted`} />
          {toApiError(record.data.draftError)?.details.reason === "no_active_policy_covering_incident" && (
            <p>
              {record.data.incident.policy_id
                ? "No active policy covers this kind of incident."
                : "This incident happened outside the policy's cover period, so the policy doesn't cover it."}
            </p>
          )}
        </div>
      ) : null}

      <div>
        <Button type="submit" variant="primary" icon={FilePlus2} loading={record.isPending} loadingLabel="Recording…">
          Record incident and draft claim
        </Button>
      </div>
    </form>
  );
}
