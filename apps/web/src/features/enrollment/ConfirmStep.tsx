import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Link2, Plus, X } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { animalsQueryKey } from "../../app/use-shell-summary";
import { Button } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { ErrorNotice } from "../../components/feedback";
import { Mono } from "../../components/figures";
import { request } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { cn } from "../../lib/cn";
import { ApiError } from "../../lib/errors";
import { confirmEnrollment, type ConfirmInput } from "./api";
import {
  OVERRIDE_COPY,
  overrideReasons,
  proposedCandidate,
  registersPending,
  type AnimalIn,
  type Decision,
  type Enrollment,
} from "./rules";
import { sampleFor } from "./samples";

type AnimalList = components["schemas"]["AnimalList"];

const FIELD = "min-h-12 w-full rounded-control border-2 border-line-strong bg-bg px-3 text-base text-ink hover:border-ink focus-visible:border-ink";
const LABEL = "text-sm font-bold";

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: (id: string, describedBy?: string) => ReactNode }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      {children(id, hint || error ? hintId : undefined)}
      {(hint || error) && (
        <p id={hintId} className={cn("text-sm", error ? "font-bold text-danger" : "text-muted")}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

const DECISIONS: { value: Decision; label: string }[] = [
  { value: "register_new", label: "Register as new" },
  { value: "link_existing", label: "Link to an animal" },
  { value: "reject", label: "Reject" },
];

export interface ConfirmStepProps {
  enrollment: Enrollment;
  decision: Decision;
  linkTo: string | null;
  onDecisionChange: (decision: Decision, linkTo: string | null) => void;
  onBack: () => void;
  onConfirmed: (enrollment: Enrollment, animal: { id: string | null; name: string | null }) => void;
}

export function ConfirmStep({ enrollment, decision, linkTo, onDecisionChange, onBack, onConfirmed }: ConfirmStepProps) {
  const proposed = sampleFor(enrollment.sample_key)?.proposed;
  const candidate = proposedCandidate(enrollment.identity);
  const [animal, setAnimal] = useState<AnimalIn>({
    name: proposed?.name ?? "",
    breed: proposed?.breed ?? "",
    breed_category: proposed?.breed_category ?? "beef",
    sex: proposed?.sex ?? "F",
    birth_date: null,
  });
  const [note, setNote] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const groupId = useId();

  const herd = useQuery({
    queryKey: animalsQueryKey,
    queryFn: () => request<AnimalList>("/animals"),
    enabled: decision === "link_existing",
  });

  const overrides = overrideReasons(enrollment, decision, linkTo);
  const needsNote = overrides.length > 0;
  const pending = decision === "register_new" && registersPending(enrollment);
  const linkedName =
    herd.data?.items.find((a) => a.id === linkTo)?.name ?? (candidate?.animal_id === linkTo ? candidate?.animal_name : null) ?? linkTo;

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (decision === "register_new") {
      if (!animal.name.trim()) errors.name = "Give the animal a name.";
      if (!animal.breed.trim()) errors.breed = "Enter the breed.";
    }
    if (decision === "link_existing" && !linkTo) errors.link_to = "Choose the animal to link to.";
    if (needsNote && !note.trim()) errors.override_note = "Write why, so the decision can be reviewed later.";
    if (decision === "reject" && !rejectReason.trim()) errors.reject_reason = "Say why the enrollment is rejected.";
    return errors;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    const body: ConfirmInput =
      decision === "register_new"
        ? {
            decision,
            animal: { ...animal, name: animal.name.trim(), breed: animal.breed.trim(), birth_date: animal.birth_date || null },
            override_note: note.trim() || null,
          }
        : decision === "link_existing"
          ? { decision, link_to: linkTo, override_note: note.trim() || null }
          : { decision, reject_reason: rejectReason.trim() };
    setSubmitting(true);
    setError(null);
    try {
      const result = await confirmEnrollment(enrollment.id, body);
      onConfirmed(result, {
        id: result.animal_id,
        name: decision === "register_new" ? animal.name.trim() : decision === "link_existing" ? (linkedName ?? null) : null,
      });
    } catch (err) {
      setError(err);
      if (err instanceof ApiError && typeof err.details.field === "string") {
        const field = err.details.field.replace(/^animal\./, "");
        setFieldErrors((prev) => ({ ...prev, [field === "animal" ? "name" : field]: err.message }));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const noteField = needsNote && (
    <Field
      label={decision === "link_existing" ? "Reason for linking to this animal" : "Reason for registering as new"}
      hint={`Needed because ${overrides.map((o) => OVERRIDE_COPY[o]).join(", and ")}. It is kept with the decision in the audit trail.`}
      error={fieldErrors.override_note}
    >
      {(id, describedBy) => (
        <textarea
          id={id}
          aria-describedby={describedBy}
          aria-invalid={fieldErrors.override_note ? true : undefined}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          className={cn(FIELD, "py-2")}
          placeholder="For example: different ear notch and coat; Bima is in Pen B today."
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex max-w-3xl flex-col gap-8">
      <fieldset className="flex flex-col gap-3">
        <legend id={groupId} className="mb-3 text-md font-bold">
          Decision
        </legend>
        <div className="flex flex-wrap gap-2">
          {DECISIONS.map((option) => {
            const checked = option.value === decision;
            return (
              <label
                key={option.value}
                className={cn(
                  "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control border-2 px-4 font-bold",
                  "has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink",
                  checked ? "border-ink bg-ink text-white" : "border-ink bg-bg hover:bg-surface-2",
                  option.value === "reject" && !checked && "border-danger text-danger",
                  option.value === "reject" && checked && "border-danger bg-danger",
                )}
              >
                <input
                  type="radio"
                  name="decision"
                  value={option.value}
                  checked={checked}
                  className="sr-only"
                  onChange={() =>
                    onDecisionChange(option.value, option.value === "link_existing" ? (linkTo ?? candidate?.animal_id ?? null) : null)
                  }
                />
                {option.label}
              </label>
            );
          })}
        </div>
      </fieldset>

      {decision === "register_new" && (
        <div className="flex flex-col gap-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name" error={fieldErrors.name}>
              {(id, d) => (
                <input
                  id={id}
                  aria-describedby={d}
                  aria-invalid={fieldErrors.name ? true : undefined}
                  className={FIELD}
                  value={animal.name}
                  onChange={(e) => setAnimal({ ...animal, name: e.target.value })}
                  autoComplete="off"
                />
              )}
            </Field>
            <Field label="Breed" error={fieldErrors.breed}>
              {(id, d) => (
                <input
                  id={id}
                  aria-describedby={d}
                  aria-invalid={fieldErrors.breed ? true : undefined}
                  className={FIELD}
                  value={animal.breed}
                  onChange={(e) => setAnimal({ ...animal, breed: e.target.value })}
                  autoComplete="off"
                />
              )}
            </Field>
            <Field label="Category">
              {(id) => (
                <select id={id} className={FIELD} value={animal.breed_category} onChange={(e) => setAnimal({ ...animal, breed_category: e.target.value })}>
                  <option value="beef">Beef</option>
                  <option value="dairy">Dairy</option>
                  <option value="dual_purpose">Dual purpose</option>
                </select>
              )}
            </Field>
            <Field label="Sex">
              {(id) => (
                <select id={id} className={FIELD} value={animal.sex} onChange={(e) => setAnimal({ ...animal, sex: e.target.value as "F" | "M" })}>
                  <option value="F">Female</option>
                  <option value="M">Male</option>
                </select>
              )}
            </Field>
            <Field label="Birth date (optional)" hint="Leave empty if unknown; the age range stays an estimate." error={fieldErrors.birth_date}>
              {(id, d) => (
                <input
                  id={id}
                  type="date"
                  aria-describedby={d}
                  className={FIELD}
                  value={animal.birth_date ?? ""}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setAnimal({ ...animal, birth_date: e.target.value || null })}
                />
              )}
            </Field>
          </div>
          {pending && (
            <p className="rounded-control border-2 border-uncertain bg-uncertain-soft p-4">
              <strong>This animal will be registered pending review.</strong> Without a confirmed muzzle identity, no
              application, payment, or claim can be prepared for it until someone confirms who it is.
            </p>
          )}
          {noteField}
        </div>
      )}

      {decision === "link_existing" && (
        <div className="flex flex-col gap-5">
          <Field label="Animal on this farm" error={fieldErrors.link_to} hint="The enrollment's views are added to this animal's references. Its valuation does not change.">
            {(id, d) => (
              <select
                id={id}
                aria-describedby={d}
                className={FIELD}
                value={linkTo ?? ""}
                onChange={(e) => onDecisionChange("link_existing", e.target.value || null)}
              >
                <option value="">Choose an animal…</option>
                {candidate && !herd.data && (
                  <option value={candidate.animal_id}>
                    {candidate.animal_name ?? candidate.animal_id} · {candidate.animal_id}
                  </option>
                )}
                {herd.data?.items.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.id}
                    {a.id === candidate?.animal_id ? " (muzzle match)" : ""}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {linkTo && (
            <div className="flex items-center gap-4">
              <EarTag animalId={linkTo} state="confirmed" size="md" />
              <p>
                <span className="font-bold">{linkedName}</span> <Mono className="text-muted">{linkTo}</Mono>
              </p>
            </div>
          )}
          {noteField}
        </div>
      )}

      {decision === "reject" && (
        <Field label="Why reject this enrollment?" error={fieldErrors.reject_reason} hint="The record is kept with your reason. You can retry with a new video afterwards.">
          {(id, d) => (
            <textarea
              id={id}
              aria-describedby={d}
              aria-invalid={fieldErrors.reject_reason ? true : undefined}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              className={cn(FIELD, "py-2")}
              placeholder="For example: wrong animal in the body view."
            />
          )}
        </Field>
      )}

      {error ? <ErrorNotice error={error} title={error instanceof ApiError ? error.message : undefined} /> : null}

      <div className="flex flex-wrap items-center gap-3 border-t-2 border-ink pt-5">
        {decision === "register_new" && (
          <Button type="submit" variant="primary" size="decision" icon={Plus} loading={submitting} loadingLabel="Registering…">
            Register {animal.name.trim() || "the animal"}
            {pending ? " as pending" : ""}
          </Button>
        )}
        {decision === "link_existing" && (
          <Button type="submit" variant="primary" size="decision" icon={Link2} loading={submitting} loadingLabel="Linking…">
            Link to {linkedName ?? "the animal"}
          </Button>
        )}
        {decision === "reject" && (
          <Button type="submit" variant="danger" size="decision" icon={X} loading={submitting} loadingLabel="Rejecting…">
            Reject enrollment
          </Button>
        )}
        <Button variant="ghost" icon={ArrowLeft} onClick={onBack} className="sm:ml-auto">
          Back to review
        </Button>
      </div>
    </form>
  );
}
