import { agentHref } from "../agent/api";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical, Send, Bot } from "lucide-react";
import { useId } from "react";
import { Link, useParams } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Money, Mono, Timestamp } from "../../components/figures";
import { PageHeader, Section } from "../../components/layout";
import { Stamp } from "../../components/Stamp";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { tagStateFor } from "../../lib/animal";
import { toApiError } from "../../lib/errors";
import { formatMoney } from "../../lib/format";
import { useRole, type Role } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import { ActionReview, useActions, type AgentAction } from "../actions";
import { closedNote, isOpen, latestAction } from "../finance/actions";
import { refreshFinance, useReviseAction, useAlerts, useAnimals, usePolicies, useProposeAction, type ChecklistItem, type Claim } from "../finance/api";
import { useClaim, useConfirmDeclaration, useIncident } from "./api";
import { EvidenceChecklist } from "./EvidenceChecklist";
import { IdentityCheckStep } from "./IdentityCheck";
import { FarmerReport, ObservedAlerts, ProfessionalFindings } from "./EvidenceKinds";
import { checklistLabel, claimStatus, isSubmitted } from "./labels";

function Declaration({ claim, role }: { claim: Claim; role: Role }) {
  const id = useId();
  const confirm = useConfirmDeclaration(claim.id);
  if (role !== "manager") return <p className="text-muted">A manager confirms the farmer declaration.</p>;
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-control border-2 border-ink px-3 py-2 font-bold">
        <input
          id={id}
          type="checkbox"
          className="size-5 flex-none accent-[var(--ink)]"
          checked={claim.declaration_confirmed || confirm.isPending}
          disabled={confirm.isPending || claim.declaration_confirmed}
          onChange={(e) => e.target.checked && confirm.mutate()}
        />
        I confirm these incident facts are accurate
      </label>
      {confirm.error ? <ErrorNotice error={confirm.error} /> : null}
    </div>
  );
}

function fixFor(item: ChecklistItem, claim: Claim, role: Role) {
  switch (item.key) {
    case "vet_assessment":
    case "vet_health_record":
      return (
        <a href="#assessment" className="font-bold">
          Ask the vet to add an assessment
        </a>
      );
    case "farmer_declaration":
      return <Declaration claim={claim} role={role} />;
    case "observation_evidence":
      return (
        <span>
          Camera alerts are linked when the incident is recorded. <Link to="/monitor">Find this animal's alert in Monitor</Link>,
          then record the incident from it.
        </span>
      );
    case "ownership_document":
      return <Link to={`/animals/${claim.animal_id}`}>Add an ownership document on the passport</Link>;
    case "active_policy":
      return <Link to={`/animals/${claim.animal_id}/insurance`}>Check the cover for this animal</Link>;
    case "identity_verified":
      return (
        <a href="#verify-identity" className="font-bold">
          Scan the muzzle to verify identity
        </a>
      );
    default:
      return null;
  }
}

function Payout({ claim, deductibleMinor, insuredMinor }: { claim: Claim; deductibleMinor?: number; insuredMinor?: number }) {
  const payout = claim.illustrative_payout;
  if (!payout) return <p className="text-muted">This product's sample terms don't state a payout formula. Sandbox Mutual assesses the claim.</p>;
  const currency = payout.currency;
  const fmt = (minor: number) => formatMoney(minor, currency, { bare: true });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="font-bold">Illustrative payout</span>
        <Money minor={payout.amount_minor} currency={currency} className="text-lg font-bold" />
      </div>
      <p className="figures text-sm break-words">max(0, min(loss, limit) − deductible)</p>
      {deductibleMinor !== undefined && insuredMinor !== undefined && (
        <p className="figures text-sm break-words text-muted">
          max(0, min({fmt(claim.claimed_amount_minor)}, {fmt(insuredMinor)}) − {fmt(deductibleMinor)}) = {fmt(payout.amount_minor)} {currency}
        </p>
      )}
      <p className="text-sm">
        <StatusPill tone="neutral" icon={FlaskConical} label="Illustrative" className="mr-2 align-middle" />
        Not a guaranteed payout. Sandbox Mutual assesses the claim. <Mono className="text-muted">{payout.terms_ref}</Mono>
      </p>
    </div>
  );
}

function Submission({ claim, actions, role, animal }: { claim: Claim; actions: readonly AgentAction[] | undefined; role: Role; animal: { id: string; name: string; tagState: ReturnType<typeof tagStateFor> } }) {
  const propose = useProposeAction();
  const toast = useToast();
  const queryClient = useQueryClient();
  const revise = useReviseAction();
  const submission = latestAction(actions, "CLAIM_SUBMISSION", claim.id);
  const blocked = claim.blocked_reason as { missing?: string[]; at?: string } | null;
  const proposeError = toApiError(propose.error);
  const missingFromError = proposeError?.code === "EVIDENCE_INCOMPLETE" ? (proposeError.details.missing as string[] | undefined) : undefined;
  // A refusal names what was missing then; list only what the current checklist still lacks.
  const stillMissing = new Set(claim.checklist.filter((item) => item.status === "missing").map((item) => item.key));
  const missing = (missingFromError ?? blocked?.missing)?.filter((key) => stillMissing.has(key));

  const prepare = () =>
    propose.mutate(
      { action_type: "CLAIM_SUBMISSION", claim_id: claim.id, animal_id: claim.animal_id },
      { onSuccess: () => toast.show({ tone: "ok", title: "Claim submission prepared — awaiting your stamp", body: "Review exactly what will be sent below." }) },
    );

  if (isSubmitted(claim.status)) {
    const receipt = (claim.receipt ?? {}) as { claim_ref?: string; received_at?: string };
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Stamp kind="posted" at={receipt.received_at} by="SANDBOX MUTUAL" />
          <StatusPill tone="awaiting" label="Assessment pending" />
        </div>
        <p>
          Sandbox Mutual received the claim{receipt.claim_ref && <> under receipt <Mono>{receipt.claim_ref}</Mono></>}
          {receipt.received_at && (
            <>
              {" "}
              on <Timestamp value={receipt.received_at} mode="absolute" />
            </>
          )}
          . The insurer's assessor decides the outcome; nothing is paid yet.
        </p>
        <p className="text-sm text-muted">Sandbox receipt · no real claim was filed.</p>
      </div>
    );
  }

  if (submission && isOpen(submission)) {
    return (
      <ActionReview
        actionId={submission.id}
        animal={animal}
        onSettled={() => void refreshFinance(queryClient)}
        onNewVersion={(next) => {
          if (!next) revise.mutate(submission.id);
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {missing && missing.length > 0 && (
        <div role="alert" className="rounded-control border-2 border-uncertain bg-uncertain-soft p-4">
          <p className="font-bold">The agent refused to prepare the submission</p>
          <p>The claim terms need every item on file. Still missing:</p>
          <ul className="mt-1 list-disc pl-5">
            {missing.map((key) => (
              <li key={key}>{checklistLabel(key)}</li>
            ))}
          </ul>
          {blocked?.at && (
            <p className="mt-2 text-sm text-muted">
              Last attempt <Timestamp value={blocked.at} mode="relative" /> · code <Mono>EVIDENCE_INCOMPLETE</Mono>
            </p>
          )}
        </div>
      )}
      {propose.error && !missingFromError ? <ErrorNotice error={propose.error} /> : null}
      {closedNote(submission, "submission") && (
        <p className={submission?.status === "failed" ? "text-danger" : "text-muted"}>{closedNote(submission, "submission")}</p>
      )}
      <p className="text-muted">
        The agent assembles the evidence manifest and the claim for Sandbox Mutual. It waits for a manager's stamp before anything is
        sent.
      </p>
      <div>
        <Button variant="primary" icon={Send} disabled={role === "vet"} loading={propose.isPending} loadingLabel="Preparing…" onClick={prepare}>
          Prepare claim submission
        </Button>
      </div>
    </div>
  );
}

export function ClaimPage() {
  const { claimId = "" } = useParams();
  const role = useRole();
  const claim = useClaim(claimId);
  const incident = useIncident(claim.data?.incident_id);
  const animals = useAnimals();
  const policies = usePolicies(claim.data?.animal_id);
  const alerts = useAlerts(claim.data?.animal_id, Boolean(claim.data));
  const actions = useActions({ animal_id: claim.data?.animal_id }, Boolean(claim.data));

  if (claim.isPending) {
    return (
      <Page>
        <LoadingRegion label="Loading the claim">
          <div className="flex flex-col gap-6">
            <Skeleton height="64px" width="420px" />
            <Skeleton height="360px" />
          </div>
        </LoadingRegion>
      </Page>
    );
  }
  if (claim.error || !claim.data) {
    return (
      <Page>
        <PageHeader title="Claim" meta={<Mono>{claimId}</Mono>} />
        <ErrorNotice error={claim.error} title="This claim couldn't load" onRetry={() => void claim.refetch()} retrying={claim.isRefetching} />
      </Page>
    );
  }

  const c = claim.data;
  const row = animals.data?.items.find((a) => a.id === c.animal_id);
  const animal = { id: c.animal_id, name: row?.name ?? c.animal_id, tagState: tagStateFor(row?.identity_status) };
  const policy = policies.data?.find((p) => p.id === c.policy_id);
  const status = claimStatus(c.status);
  const submitted = isSubmitted(c.status);
  const needs = c.checklist
    .filter((i) => i.status === "missing" && (i.key === "vet_assessment" || i.key === "vet_health_record"))
    .map((i) => i.key as "vet_assessment" | "vet_health_record");

  return (
    <Page>
      <PageHeader
        lead={<EarTag animalId={animal.id} state={animal.tagState} size="md" />}
        title={`Claim for ${animal.name}`}
        meta={
          <>
            <Mono className="text-ink">{c.id}</Mono> · {policy?.product_name ?? c.product_id ?? "Policy"} · policy <Mono>{c.policy_id}</Mono>
          </>
        }
        actions={
          <>
            <StatusPill tone={status.tone} label={status.label} />
            <ButtonLink to={agentHref(animal.id, isSubmitted(c.status) ? "track_claim" : "file_claim")} variant="secondary" icon={Bot}>
              Help me with this claim
            </ButtonLink>
            <Link to="/claims" className="inline-flex min-h-11 items-center gap-2 font-bold">
              <ArrowLeft aria-hidden="true" className="size-5" strokeWidth={2.25} />
              All claims
            </Link>
          </>
        }
      />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(360px,440px)] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-6">
          <h2 className="text-lg font-bold">Evidence on file</h2>
          {incident.isPending ? (
            <Skeleton height="240px" />
          ) : incident.error || !incident.data ? (
            <ErrorNotice error={incident.error} title="The incident couldn't load" onRetry={() => void incident.refetch()} />
          ) : (
            <>
              <FarmerReport incident={incident.data} />
              <ProfessionalFindings incident={incident.data} role={role.role} needs={needs} locked={submitted} />
              <ObservedAlerts
                alertIds={incident.data.linked_alert_ids}
                alerts={alerts.data}
                actions={actions.data}
                role={role.role}
                canNotify={policy?.status === "active"}
              />
            </>
          )}
        </div>

        <div className="flex min-w-0 flex-col">
          {(c.identity_check_required || (c.identity_checks ?? []).length > 0) && (
            <Section
              anchor="verify-identity"
              className="scroll-mt-24"
              title="Verify identity"
              description={`Scan the muzzle of the dead animal; VEYRA compares it with the muzzle enrolled for ${animal.name}.`}
            >
              <IdentityCheckStep claim={c} animalName={animal.name} role={role.role} locked={submitted} />
            </Section>
          )}
          <Section title="Evidence checklist" description="What the sample claim terms require before submission.">
            <EvidenceChecklist items={c.checklist} renderFix={(item) => (submitted ? null : fixFor(item, c, role.role))} />
          </Section>
          <Section title="Payout">
            <Payout claim={c} deductibleMinor={policy?.deductible_minor} insuredMinor={policy?.insured_value_minor} />
          </Section>
          <Section title="Submission">
            <Submission claim={c} actions={actions.data} role={role.role} animal={animal} />
          </Section>
        </div>
      </div>
    </Page>
  );
}
