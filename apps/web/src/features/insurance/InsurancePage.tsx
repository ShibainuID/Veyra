import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, FileSignature, Lock, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Money, Mono } from "../../components/figures";
import { PageHeader, Section } from "../../components/layout";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { api } from "../../lib/api";
import { tagStateFor } from "../../lib/animal";
import { useRole } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import { useActions, type AgentAction } from "../actions";
import { approvalsHref, closedNote, isOpen, latestAction } from "../finance/actions";
import { financeKeys, usePassport, usePolicies, useProposeAction, type Passport, type Recommendation } from "../finance/api";
import { formatDate } from "../finance/dates";
import { ComparisonTable } from "./ComparisonTable";
import { CurrentCover, currentPolicy } from "./CurrentCover";
import { ExplanationPanel } from "./ExplanationPanel";

function useRecommendations(animalId: string, enabled: boolean) {
  return useQuery({
    queryKey: financeKeys.recommendations(animalId),
    enabled,
    staleTime: 60_000,
    queryFn: async () =>
      (await api.POST("/api/v1/animals/{animal_id}/insurance-recommendations", { params: { path: { animal_id: animalId } } }))
        .data!,
  });
}

function BasisLine({ passport, insuredMinor, currency }: { passport: Passport; insuredMinor: number | null; currency: string }) {
  const valuation = passport.animal.valuation;
  if (!valuation || insuredMinor === null) {
    return (
      <EmptyState
        title="No confirmed valuation yet"
        icon={ShieldAlert}
        action={
          <ButtonLink to={`/animals/${passport.animal.id}#valuation`} variant="primary" icon={ArrowRight}>
            Open the valuation on the passport
          </ButtonLink>
        }
      >
        Cover is written up to the lower bound of a manager-confirmed indicative value, so no product can be priced until a
        valuation is confirmed on {passport.animal.name}'s passport.
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-1 border-y-2 border-ink py-4">
      <p className="text-md">
        Cover is written up to the lower bound of the confirmed indicative value:{" "}
        <Money minor={insuredMinor} currency={currency} className="font-bold" /> ·{" "}
        <span className="text-muted">
          valuation <Mono>v{valuation.version}</Mono> · price <Mono>{formatDate(valuation.price_date)}</Mono> · range{" "}
          <Money low={valuation.value_low_minor} high={valuation.value_high_minor} currency={valuation.currency} />
        </span>
      </p>
      <p className="text-muted">Indicative value is not an insurer-agreed value or a payout.</p>
    </div>
  );
}

interface ActionContext {
  identityConfirmed: boolean;
  canPrepare: boolean;
  hasCover: boolean;
  coverName?: string;
  pendingApplication?: AgentAction;
  /** The newest application, when it closed without running (declined, expired, stale). */
  closedApplication?: AgentAction;
  preparing: string | null;
  onPrepare: (result: Recommendation) => void;
}

/** Printed once under the comparison when the animal already has cover: no product can be applied for. */
function CoveredNote({ coverName }: { coverName?: string }) {
  return <p className="text-sm text-muted">{coverName ? `Already covered under ${coverName}.` : "This animal already has cover."}</p>;
}

function ProductAction({ result, ctx }: { result: Recommendation; ctx: ActionContext }) {
  const pending = ctx.pendingApplication;
  if (pending) {
    const mine = (pending.payload as { product_id?: string }).product_id === result.product_id;
    if (!mine) return <p className="text-sm text-muted">Another application for this animal is waiting.</p>;
    return (
      <div className="flex flex-col items-start gap-3">
        <StatusPill tone="awaiting" label="Awaiting your stamp" />
        <ButtonLink to={approvalsHref(pending.id)} variant="secondary" icon={ArrowRight}>
          Review the application
        </ButtonLink>
      </div>
    );
  }
  if (ctx.hasCover) return <CoveredNote coverName={ctx.coverName} />;
  if (result.outcome === "ineligible") return <p className="text-sm text-muted">Not available for this animal under the sample terms.</p>;
  if (result.outcome === "unknown") return <p className="text-sm text-muted">Resolve the review item above before applying.</p>;
  const closed = ctx.closedApplication;
  const note = closed && (closed.payload as { product_id?: string }).product_id === result.product_id ? closedNote(closed, "application") : null;
  return (
    <div className="flex flex-col items-start gap-2">
      {note && <p className="text-sm text-muted">{note}</p>}
      <Button
        variant="primary"
        icon={FileSignature}
        disabled={!ctx.identityConfirmed || !ctx.canPrepare || (ctx.preparing !== null && ctx.preparing !== result.product_id)}
        loading={ctx.preparing === result.product_id}
        loadingLabel="Preparing…"
        onClick={() => ctx.onPrepare(result)}
      >
        Prepare application
      </Button>
      {!ctx.canPrepare && (
        <span className="flex items-center gap-2 text-sm text-muted">
          <Lock aria-hidden="true" className="size-4" strokeWidth={2.25} />A manager or operator prepares applications.
        </span>
      )}
      <span className="text-sm text-muted">Nothing is sent until a manager stamps it.</span>
    </div>
  );
}

export function InsurancePage() {
  const { animalId = "" } = useParams();
  const role = useRole();
  const toast = useToast();
  const passport = usePassport(animalId);
  const canRecommend = role.role !== "vet";
  const recs = useRecommendations(animalId, Boolean(passport.data) && canRecommend);
  const policies = usePolicies(animalId);
  const actions = useActions({ animal_id: animalId });
  const propose = useProposeAction();

  if (passport.isPending) {
    return (
      <Page>
        <LoadingRegion label="Loading this animal's coverage">
          <div className="flex flex-col gap-6">
            <Skeleton height="64px" width="420px" />
            <Skeleton lines={2} />
            <Skeleton height="420px" />
          </div>
        </LoadingRegion>
      </Page>
    );
  }
  if (passport.error || !passport.data) {
    return (
      <Page>
        <PageHeader title="Coverage" meta={<Mono>{animalId}</Mono>} />
        <ErrorNotice error={passport.error} title="This animal couldn't load" onRetry={() => void passport.refetch()} retrying={passport.isRefetching} />
      </Page>
    );
  }

  const animal = passport.data.animal;
  const identityConfirmed = animal.identity_status === "confirmed";
  const policy = currentPolicy(policies.data);
  const application = latestAction(actions.data, "POLICY_APPLICATION", animal.id);
  const pendingApplication = application && isOpen(application) ? application : undefined;

  const ctx: ActionContext = {
    identityConfirmed,
    canPrepare: role.role !== "vet",
    hasCover: Boolean(policy),
    coverName: policy?.product_name ?? undefined,
    pendingApplication,
    closedApplication: application && !isOpen(application) ? application : undefined,
    preparing: propose.isPending ? ((propose.variables?.product_id as string | undefined) ?? null) : null,
    onPrepare: (result) =>
      propose.mutate(
        { action_type: "POLICY_APPLICATION", animal_id: animal.id, product_id: result.product_id },
        {
          onSuccess: () =>
            toast.show({
              tone: "ok",
              title: "Application prepared — awaiting your stamp",
              body: `${result.product_name} for ${animal.name}. It waits in Approvals and on the passport.`,
            }),
        },
      ),
  };

  return (
    <Page>
      <PageHeader
        lead={<EarTag animalId={animal.id} state={tagStateFor(animal.identity_status)} size="md" />}
        title={`Coverage for ${animal.name}`}
        meta={
          <>
            <Mono className="text-ink">{animal.id}</Mono> · {animal.breed} · sample terms from Sandbox Mutual
          </>
        }
        actions={
          <Link to={`/animals/${animal.id}`} className="inline-flex min-h-11 items-center gap-2 font-bold">
            <ArrowLeft aria-hidden="true" className="size-5" strokeWidth={2.25} />
            Back to the passport
          </Link>
        }
      />

      {!identityConfirmed && (
        <div role="alert" className="mb-6 flex gap-3 rounded-control border-2 border-uncertain bg-uncertain-soft p-4">
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-5 flex-none text-uncertain-ink" strokeWidth={2.25} />
          <div>
            <p className="font-bold">Identity not confirmed</p>
            <p>
              Confirm {animal.name}'s identity before any financial action. Products are shown for reference, but nothing can
              be prepared yet. <Link to={`/animals/${animal.id}`}>Review the identity on the passport</Link>.
            </p>
          </div>
        </div>
      )}

      {policy && (
        <Section title="Current cover" className="mb-12">
          <CurrentCover policy={policy} actions={actions.data} role={role.role} />
        </Section>
      )}

      {propose.error ? <ErrorNotice error={propose.error} title="The application couldn't be prepared" className="mb-6" /> : null}

      {!canRecommend ? (
        <ErrorNotice code="FORBIDDEN_ROLE" title="Product comparison is for managers and operators" />
      ) : recs.isPending ? (
        <LoadingRegion label="Checking the sample products against this animal">
          <div className="flex flex-col gap-4">
            <Skeleton lines={2} />
            <Skeleton height="480px" />
          </div>
        </LoadingRegion>
      ) : recs.error || !recs.data ? (
        <ErrorNotice error={recs.error} title="The products couldn't be checked" onRetry={() => void recs.refetch()} retrying={recs.isRefetching} />
      ) : (
        <>
          <BasisLine passport={passport.data} insuredMinor={recs.data.insured_value_minor} currency={recs.data.currency} />
          <Section
            title="Compare sample products"
            description={
              <>
                Each product checked against {animal.name}'s passport, under terms <Mono>{recs.data.catalog_version}</Mono>. These
                are fictional sample terms, not a market quote.
              </>
            }
            className="mt-10"
          >
            <ComparisonTable
              results={recs.data.results}
              renderAction={(result) => <ProductAction result={result} ctx={ctx} />}
              sharedAction={!ctx.pendingApplication && ctx.hasCover ? <CoveredNote coverName={ctx.coverName} /> : undefined}
            />
          </Section>
          <Section title="Why these outcomes">
            <ExplanationPanel explanation={recs.data.explanation} results={recs.data.results} />
          </Section>
        </>
      )}
    </Page>
  );
}
