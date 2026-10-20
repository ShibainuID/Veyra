import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Lock, RefreshCw, Wallet } from "lucide-react";
import { Button, ButtonLink } from "../../components/Button";
import { ErrorNotice } from "../../components/feedback";
import { Money, Mono } from "../../components/figures";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { api } from "../../lib/api";
import type { Role } from "../../lib/role-store";
import { approvalsHref, closedNote, isOpen, latestAction } from "../finance/actions";
import { refreshFinance, useProposeAction, type AgentAction, type Policy } from "../finance/api";
import { receiptRef } from "../actions";
import { formatDate, newIdempotencyKey } from "../finance/dates";

const POLICY_STATUS: Record<string, { tone: StatusTone; label: string }> = {
  awaiting_payment: { tone: "awaiting", label: "Awaiting premium payment" },
  paid_pending_activation: { tone: "uncertain", label: "Paid, not yet active" },
  active: { tone: "ok", label: "Active" },
};

export function policyStatus(status: string): { tone: StatusTone; label: string } {
  return POLICY_STATUS[status] ?? { tone: "neutral", label: status.replace(/_/g, " ") };
}

/** Policies that still matter on this screen (not lapsed or cancelled). */
export function currentPolicy(policies: readonly Policy[] | undefined): Policy | undefined {
  return (policies ?? [])
    .filter((p) => p.status in POLICY_STATUS)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
}

interface CurrentCoverProps {
  policy: Policy;
  actions: readonly AgentAction[] | undefined;
  role: Role;
}

/** The policy this animal already has, with the one next step it is waiting on. */
export function CurrentCover({ policy, actions, role }: CurrentCoverProps) {
  const status = policyStatus(policy.status);
  return (
    <div className="flex flex-col gap-5 rounded-panel border-2 border-ink p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="text-md font-bold">{policy.product_name ?? policy.product_id}</h3>
          <p className="text-sm text-muted">
            Sandbox Mutual · terms <Mono>{policy.terms_version}</Mono> · policy <Mono>{policy.id}</Mono>
          </p>
        </div>
        <StatusPill tone={status.tone} label={status.label} />
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm text-muted">Insured value</dt>
          <dd className="font-bold">
            <Money minor={policy.insured_value_minor} currency={policy.currency} />
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm text-muted">Premium a year</dt>
          <dd className="font-bold">
            <Money minor={policy.premium_minor} currency={policy.currency} />
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm text-muted">Deductible</dt>
          <dd className="font-bold">
            <Money minor={policy.deductible_minor} currency={policy.currency} />
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-sm text-muted">Cover period</dt>
          <dd className="figures font-bold">
            {policy.effective_date ? `${formatDate(policy.effective_date)} – ${formatDate(policy.expiry_date)}` : "Not started"}
          </dd>
        </div>
      </dl>
      <NextStep policy={policy} actions={actions} role={role} />
    </div>
  );
}

function NextStep({ policy, actions, role }: CurrentCoverProps) {
  if (policy.status === "awaiting_payment") return <PaymentStep policy={policy} actions={actions} role={role} />;
  if (policy.status === "paid_pending_activation") return <ActivationStep policy={policy} role={role} />;
  const ref = receiptRef(policy.activation_receipt);
  return (
    <p className="border-t border-line pt-4">
      Sandbox Mutual confirmed this cover
      {ref && (
        <>
          {" "}
          under <Mono>{ref}</Mono>
        </>
      )}
      . It runs from <Mono>{formatDate(policy.effective_date)}</Mono> to <Mono>{formatDate(policy.expiry_date)}</Mono>.
    </p>
  );
}

function PaymentStep({ policy, actions, role }: CurrentCoverProps) {
  const propose = useProposeAction();
  const toast = useToast();
  const payment = latestAction(actions, "PREMIUM_PAYMENT", policy.application_id ?? undefined);
  const canPrepare = role !== "vet";

  if (payment && isOpen(payment)) {
    const unresolved = payment.status === "executing" || payment.status === "unknown";
    return (
      <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p>
          {unresolved
            ? "The payment's outcome is not known yet. Reconcile it in Approvals with the same key; it will not charge twice."
            : "A premium payment of "}
          {!unresolved && (
            <>
              <Money minor={policy.premium_minor} currency={policy.currency} /> is waiting for your stamp.
            </>
          )}
        </p>
        <ButtonLink to={approvalsHref(payment.id)} variant="secondary" icon={ArrowRight}>
          {unresolved ? "Reconcile in Approvals" : "Review the payment"}
        </ButtonLink>
      </div>
    );
  }

  const failed = payment?.status === "failed" ? payment : undefined;
  const failure = failed?.execution?.error as { message?: string } | null | undefined;
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      {!failed && closedNote(payment, "premium payment") && <p className="text-muted">{closedNote(payment, "premium payment")}</p>}
      {failed && (
        <div role="status" className="rounded-control border-2 border-danger bg-danger-soft p-4">
          <p className="font-bold">The last premium payment failed</p>
          <p>
            {failure?.message ?? "The sandbox payment provider declined it."} The hold was released, so nothing left the
            wallet. The cover stays unpaid until a new payment posts.
          </p>
        </div>
      )}
      <p>
        Sandbox Mutual accepted the application
        {policy.application_id && (
          <>
            {" "}
            (<Mono>{policy.application_id}</Mono>)
          </>
        )}
        . Cover starts only after the premium of <Money minor={policy.premium_minor} currency={policy.currency} /> is paid
        and the insurer confirms.
      </p>
      {propose.error ? <ErrorNotice error={propose.error} /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          icon={Wallet}
          disabled={!canPrepare || !policy.application_id}
          loading={propose.isPending}
          loadingLabel="Preparing…"
          onClick={() =>
            propose.mutate(
              { action_type: "PREMIUM_PAYMENT", policy_application_id: policy.application_id, animal_id: policy.animal_id },
              {
                onSuccess: (action) =>
                  toast.show({
                    tone: "ok",
                    title: "Payment prepared — awaiting your stamp",
                    body: `${action.id} waits in Approvals for a manager's stamp.`,
                  }),
              },
            )
          }
        >
          {failed ? "Prepare the payment again" : "Prepare premium payment"}
        </Button>
        {!canPrepare && (
          <span className="flex items-center gap-2 text-sm text-muted">
            <Lock aria-hidden="true" className="size-4" strokeWidth={2.25} />A manager or operator prepares payments.
          </span>
        )}
      </div>
    </div>
  );
}

function ActivationStep({ policy, role }: { policy: Policy; role: Role }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const check = useMutation({
    mutationFn: async () =>
      (
        await api.POST("/api/v1/policies/{policy_id}/activation-check", {
          params: { path: { policy_id: policy.id }, header: { "Idempotency-Key": newIdempotencyKey() } },
        })
      ).data!,
    onSuccess: (updated) => {
      toast.show(
        updated.status === "active"
          ? { tone: "ok", title: "Cover is active", body: `Sandbox Mutual confirmed it from ${formatDate(updated.effective_date)}.` }
          : { tone: "neutral", title: "Not confirmed yet", body: "Sandbox Mutual has not confirmed activation. Check again later." },
      );
    },
    onSettled: () => refreshFinance(queryClient),
  });
  const canCheck = role === "manager";
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <p className="font-bold">Waiting for Sandbox Mutual to confirm activation</p>
      <p className="max-w-[70ch]">
        The premium is paid. Coverage is not active until the insurer confirms it, and a claim can't be drafted before then.
      </p>
      {check.error ? <ErrorNotice error={check.error} /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" icon={RefreshCw} disabled={!canCheck} loading={check.isPending} loadingLabel="Checking…" onClick={() => check.mutate()}>
          Check activation
        </Button>
        {!canCheck && (
          <span className="flex items-center gap-2 text-sm text-muted">
            <Lock aria-hidden="true" className="size-4" strokeWidth={2.25} />
            Only a manager can check activation.
          </span>
        )}
      </div>
    </div>
  );
}
