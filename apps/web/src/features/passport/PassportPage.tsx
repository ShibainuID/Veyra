import { ArrowRight, Bot, Cctv, FileCheck2, ShieldCheck, Siren, Stamp as StampIcon, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { ButtonLink } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { EvidenceFrame, type EvidenceView } from "../../components/EvidenceFrame";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Money, Mono, Range, TimeWindow, Timestamp } from "../../components/figures";
import { PageHeader, Section } from "../../components/layout";
import { NotGuaranteed } from "../../components/NotGuaranteed";
import { Provenance } from "../../components/Provenance";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { alertKindLabel, asSource, healthPill, humanize, identityPill, productName, providerName, sexWord, tagStateFor } from "../../lib/animal";
import { agentHref } from "../../lib/agent-link";
import { toApiError } from "../../lib/errors";
import { formatMoney, lineNumber } from "../../lib/format";
import { useNow } from "../../lib/use-now";
import { NotFoundPage } from "../../pages/NotFoundPage";
import { Page } from "../../pages/Page";
import { actionTitle } from "../actions/types";
import { AnimalPassbook } from "../passbook/AnimalPassbook";
import { useObservations, usePassport, type Passport } from "./api";
import { CameraGallery } from "./CameraGallery";
import { DocumentsSection } from "./DocumentsSection";
import { ValuationSection } from "./ValuationSection";
import { reasonCopy } from "../enrollment/review-copy";

const VIEWS: readonly EvidenceView[] = ["muzzle", "teeth", "body"];
const STALE_AFTER_MS = 60 * 60_000;

function Facts({ children }: { children: ReactNode }) {
  return <dl className="grid gap-x-8 gap-y-0 sm:grid-cols-2">{children}</dl>;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-line py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="rounded-control border-2 border-dashed border-line-strong p-4 text-muted">{children}</p>;
}

function IdentitySection({ passport }: { passport: Passport }) {
  const { animal, references } = passport;
  const pill = identityPill(animal.identity_status);
  return (
    <Section title="Identity evidence" description="Each view is registered at the same scale and crop, so later visits compare frame for frame.">
      <div className="grid gap-4 sm:grid-cols-3">
        {VIEWS.map((view) => {
          const ref = references.find((r) => r.view === view);
          const note = typeof ref?.quality?.note === "string" ? ref.quality.note : null;
          return (
            <div key={view} className="flex flex-col gap-1">
              <EvidenceFrame
                view={view}
                src={ref?.crop_url ?? ref?.media_url ?? null}
                alt={`${animal.name}, ${view} view`}
                recorded={Boolean(ref)}
              />
              {ref?.frame_time_s != null && (
                <span className="text-sm text-muted">
                  Frame at <Mono>{ref.frame_time_s.toFixed(1)} s</Mono> of the enrollment video
                </span>
              )}
              {note && <span className="text-sm text-muted">{note}</span>}
            </div>
          );
        })}
      </div>
      <div className="mt-6">
        <Facts>
          <Fact label="Identity">
            <StatusPill {...pill} />
          </Fact>
          <Fact label="Confirmed by">
            {animal.confirmed_by ? (
              <span>
                {animal.confirmed_by}
                {animal.confirmed_at && (
                  <>
                    {" · "}
                    <Timestamp value={animal.confirmed_at} mode="absolute" className="text-sm" />
                  </>
                )}
              </span>
            ) : (
              <span className="text-muted">Not confirmed yet</span>
            )}
          </Fact>
          <Fact label="Enrollment">
            {animal.enrollment_id ? (
              <Link to={`/enroll?enrollment=${animal.enrollment_id}`} className="figures font-bold">
                {animal.enrollment_id}
              </Link>
            ) : (
              <span className="text-muted">No enrollment on record</span>
            )}
          </Fact>
          <Fact label="Ownership documents">
            <span className="flex flex-wrap items-center gap-2">
              {animal.ownership_doc_refs.length > 0 ? (
                <>
                  <span>
                    <Mono>{animal.ownership_doc_refs.length}</Mono> on file
                  </span>
                  <Provenance source="documented" />
                </>
              ) : (
                <span className="text-muted">None on file</span>
              )}
              <a href="#documents" className="inline-flex min-h-11 items-center font-bold">
                See documents
              </a>
            </span>
          </Fact>
        </Facts>
      </div>
    </Section>
  );
}

/** "teeth_view_missing" on an age estimate reads "No teeth frame", the same words as enrollment review. */
function estimateReviewLabel(kind: string, reason: string | null | undefined): string {
  if (!reason) return "Needs review";
  const title = reasonCopy(`${kind}_${reason}`).title;
  const prefix = `${humanize(kind)}: `;
  if (!title.startsWith(prefix)) return humanize(reason);
  const rest = title.slice(prefix.length);
  return rest.charAt(0).toUpperCase() + rest.slice(1);
}

function EstimatesSection({ passport }: { passport: Passport }) {
  const estimates = [...passport.estimates].sort((a, b) => a.kind.localeCompare(b.kind));
  return (
    <Section title="Estimates" description="Ranges, not points: each one names its method and where it came from.">
      {estimates.length === 0 ? (
        <Muted>No estimates yet. Enrollment produces age and weight ranges from the guided video.</Muted>
      ) : (
        <ul className="flex flex-col border-t-2 border-ink">
          {estimates.map((estimate) => (
            <li key={estimate.id} className="grid gap-x-6 gap-y-2 border-b border-line py-4 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-center">
              <span className="font-bold">{humanize(estimate.kind)}</span>
              <span className="flex min-w-0 flex-col gap-0.5">
                {estimate.range_low != null && estimate.range_high != null ? (
                  <Range low={estimate.range_low} high={estimate.range_high} unit={estimate.unit} className="text-md font-bold" />
                ) : (
                  <span className="text-muted">No range: the method couldn't produce one</span>
                )}
                <span className="text-sm text-muted">
                  Method <Mono>{estimate.method_version}</Mono>
                  {estimate.point != null && (
                    <>
                      {" "}
                      · midpoint <Mono>{estimate.point}</Mono> {estimate.unit}
                    </>
                  )}
                  {" · "}
                  <Timestamp value={estimate.created_at} mode="absolute" />
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <Provenance source={asSource(estimate.source)} />
                {estimate.review_required && <StatusPill tone="uncertain" label={estimateReviewLabel(estimate.kind, estimate.review_reason)} />}
              </span>
            </li>
          ))}
        </ul>
      )}
      {estimates.length > 0 && <NotGuaranteed className="mt-3" />}
    </Section>
  );
}

function policyTone(status: string): StatusTone {
  if (status === "active") return "ok";
  if (status === "pending" || status === "pending_activation" || status === "submitted") return "awaiting";
  if (status === "lapsed" || status === "cancelled" || status === "declined") return "danger";
  return "neutral";
}

/** The in-app agent's way in for this animal: find cover when there is none, file a claim when a policy is active. */
function AgentLink({ animal }: { animal: Passport["animal"] }) {
  if (animal.coverage.status === "none") {
    return (
      <ButtonLink to={agentHref(animal.id, "find_insurance")} variant="primary" icon={Bot}>
        Find insurance with the VEYRA agent
      </ButtonLink>
    );
  }
  if (animal.coverage.status === "active") {
    return (
      <ButtonLink to={agentHref(animal.id, "file_claim")} variant="primary" icon={Bot}>
        File a claim with the VEYRA agent
      </ButtonLink>
    );
  }
  return null;
}

function CoverageSection({ passport }: { passport: Passport }) {
  const { policies, applications, animal } = passport;
  const openApplications = applications.filter((app) => !policies.some((p) => p.application_id === app.id));
  const agentOffered = animal.coverage.status === "none" || animal.coverage.status === "active";
  return (
    <Section
      title="Coverage"
      anchor="coverage"
      actions={
        <>
          <AgentLink animal={animal} />
          <ButtonLink to={`/animals/${animal.id}/insurance`} variant={agentOffered ? "secondary" : "primary"} icon={ShieldCheck}>
            Compare coverage
          </ButtonLink>
        </>
      }
    >
      {policies.length === 0 && openApplications.length === 0 ? (
        <Muted>
          No active insurance. The VEYRA agent checks eligibility, compares the sandbox products, and prepares an application for your
          approval. You can also compare them yourself.
        </Muted>
      ) : (
        <ul className="flex flex-col gap-4">
          {policies.map((policy) => (
            <li key={policy.id} className="rounded-panel border-2 border-line p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-md font-bold">{policy.product_name ?? productName(policy.product_id)}</span>
                <StatusPill tone={policyTone(policy.status)} label={humanize(policy.status)} />
              </div>
              <Facts>
                <Fact label="Insured value">
                  <Money minor={policy.insured_value_minor} currency={policy.currency} className="font-bold" />
                </Fact>
                <Fact label="Premium">
                  <Money minor={policy.premium_minor} currency={policy.currency} />
                </Fact>
                <Fact label="Deductible">
                  <Money minor={policy.deductible_minor} currency={policy.currency} />
                </Fact>
                <Fact label="Cover dates">
                  {policy.effective_date ? (
                    <Mono>
                      {policy.effective_date} – {policy.expiry_date ?? "open"}
                    </Mono>
                  ) : (
                    <span className="text-muted">Starts once the insurer confirms</span>
                  )}
                </Fact>
              </Facts>
              <p className="mt-2 text-sm text-muted">
                <Mono>{policy.id}</Mono> · terms <Mono>{policy.terms_version}</Mono> · {providerName(policy.provider_id)}
              </p>
            </li>
          ))}
          {openApplications.map((app) => (
            <li key={app.id} className="rounded-panel border-2 border-dashed border-line-strong p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-md font-bold">Application · {app.product_name ?? productName(app.product_id)}</span>
                <StatusPill tone="awaiting" label={humanize(app.status)} />
              </div>
              <p className="mt-2 text-muted">
                Insured value <Money minor={app.insured_value_minor} currency={app.currency} className="text-ink" /> · premium{" "}
                <Money minor={app.premium_minor} currency={app.currency} className="text-ink" />
                {app.provider_ref && (
                  <>
                    {" "}
                    · ref <Mono className="text-ink">{app.provider_ref}</Mono>
                  </>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function LocationSection({ passport }: { passport: Passport }) {
  const observations = useObservations(passport.animal.id);
  const now = useNow(30_000);
  const cameraNames = new Map(passport.observations.cameras.map((c) => [c.camera_id, c.camera_name ?? c.camera_id]));
  const last = observations.data?.last_observation ?? null;
  const recent = observations.data?.recent ?? [];
  return (
    <Section title="Location" description="Where cameras last saw this animal. It is a sighting, not a live position.">
      {observations.isPending ? (
        <LoadingRegion label="Loading camera sightings">
          <Skeleton lines={2} />
        </LoadingRegion>
      ) : observations.error ? (
        <ErrorNotice error={observations.error} title="Camera sightings couldn't load" onRetry={() => void observations.refetch()} />
      ) : !last ? (
        <Muted>No camera observation yet. It appears here once a pen camera links a track to this animal.</Muted>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <Cctv aria-hidden="true" className="mt-1 size-6 flex-none" strokeWidth={2.25} />
            <div className="flex flex-col gap-1">
              <p className="text-md">
                Last observed at <span className="font-bold">{last.camera_name ?? last.camera_id}</span>
              </p>
              <Timestamp value={last.observed_at} />
              {now - new Date(last.observed_at).getTime() > STALE_AFTER_MS && (
                <p className="flex items-center gap-2 font-bold text-uncertain-ink">
                  <TriangleAlert aria-hidden="true" className="size-4" strokeWidth={2.25} />
                  It may have moved since.
                </p>
              )}
              {last.association_status !== "associated" && (
                <StatusPill tone="uncertain" label={`Track ${humanize(last.association_status).toLowerCase()}`} className="self-start" />
              )}
            </div>
          </div>
          {recent.length > 0 && (
            <div>
              <h3 className="mb-2 font-bold">Recent sightings</h3>
              <ul className="flex flex-col border-t border-line">
                {recent.slice(0, 8).map((obs) => (
                  <li key={obs.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line py-2.5">
                    <span>{cameraNames.get(obs.camera_id) ?? obs.camera_id}</span>
                    <span className="flex flex-wrap items-center gap-2 text-sm text-muted">
                      <Timestamp value={obs.observed_at} mode="absolute" />
                      <span>
                        visibility <Mono className="text-ink">{Math.round(obs.visibility * 100)}%</Mono>
                      </span>
                      <Provenance source={asSource(obs.source)} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <div className="mt-8">
        <CameraGallery passport={passport} />
      </div>
    </Section>
  );
}

function AlertsSection({ passport }: { passport: Passport }) {
  const alerts = [...passport.alerts].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <Section title="Alerts">
      {alerts.length === 0 ? (
        <Muted>No alerts. Movement and observation-quality alerts from the pen cameras appear here.</Muted>
      ) : (
        <ul className="flex flex-col border-t border-line">
          {alerts.map((alert) => (
            <li key={alert.id} className="border-b border-line">
              <Link to={`/alerts/${alert.id}`} className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 no-underline hover:bg-surface">
                <span className="flex items-center gap-3">
                  <Siren aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
                  <span className="flex flex-col">
                    <span className="font-bold underline-offset-4 hover:underline">{alertKindLabel(alert.kind)}</span>
                    <span className="text-sm text-muted">
                      <TimeWindow start={alert.window_start} end={alert.window_end} />
                    </span>
                  </span>
                </span>
                <StatusPill tone={alert.status === "open" ? "uncertain" : alert.status === "resolved" ? "ok" : "neutral"} label={humanize(alert.status)} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function ClaimsSection({ passport }: { passport: Passport }) {
  const { incidents, claims } = passport;
  return (
    <Section title="Claims and incidents">
      {incidents.length === 0 && claims.length === 0 ? (
        <Muted>No incidents recorded. An incident recorded for this animal can become a sandbox claim.</Muted>
      ) : (
        <ul className="flex flex-col border-t border-line">
          {claims.map((claim) => (
            <li key={claim.id} className="border-b border-line">
              <Link to={`/claims/${claim.id}`} className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 no-underline hover:bg-surface">
                <span className="flex items-center gap-3">
                  <FileCheck2 aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
                  <span className="flex flex-col">
                    <span className="font-bold">
                      Claim <Mono>{claim.id}</Mono>
                    </span>
                    <span className="text-sm text-muted">
                      Claimed <Money minor={claim.claimed_amount_minor} currency={claim.currency} />
                    </span>
                  </span>
                </span>
                <StatusPill tone={claim.status === "submitted" ? "ok" : claim.status === "blocked" ? "uncertain" : "neutral"} label={humanize(claim.status)} />
              </Link>
            </li>
          ))}
          {incidents
            .filter((incident) => !claims.some((claim) => claim.incident_id === incident.id))
            .map((incident) => (
              <li key={incident.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line py-3">
                <span className="flex flex-col">
                  <span className="font-bold">Incident · {humanize(incident.kind)}</span>
                  <span className="text-sm text-muted">
                    <Timestamp value={incident.occurred_at} mode="absolute" /> · estimated loss{" "}
                    {formatMoney(incident.estimated_loss_minor, incident.currency)}
                  </span>
                </span>
                <Link to={`/claims?incident=${incident.id}`} className="inline-flex min-h-11 items-center gap-1 font-bold">
                  Start a claim
                  <ArrowRight aria-hidden="true" className="size-4" strokeWidth={2.5} />
                </Link>
              </li>
            ))}
        </ul>
      )}
    </Section>
  );
}

/** Below 900px the passbook sits at the end of the page, so a sticky bar points to the waiting line. */
function AwaitingBar({ passport }: { passport: Passport }) {
  const line = passport.passbook.lines.find((l) => l.status === "awaiting");
  if (!line) return null;
  const pending = passport.pending_actions.find((a) => a.id === line.action_id);
  return (
    <div className="sticky bottom-[calc(var(--tabbar-height)+env(safe-area-inset-bottom))] z-sticky -mx-4 flex items-center justify-between gap-3 border-t-2 border-ink bg-bg px-4 py-3 shadow-[0_-8px_16px_-8px_oklch(0.18_0.005_260/0.18)] sm:-mx-6 sm:px-6 lg:bottom-0 tab:hidden">
      <span className="min-w-0">
        <span className="block font-bold">{pending ? actionTitle(pending.action_type) : line.title} awaits your stamp</span>
        <span className="text-sm text-muted">
          Line <Mono>{lineNumber(line.no)}</Mono>
          {line.amount_minor != null && <> · {formatMoney(line.amount_minor, line.currency ?? "USD")}</>}
        </span>
      </span>
      <a href="#passbook" className="inline-flex min-h-12 flex-none items-center gap-2 rounded-control border-2 border-ink bg-ink px-4 font-bold text-tag no-underline">
        <StampIcon aria-hidden="true" className="size-5" strokeWidth={2.25} />
        Review
      </a>
    </div>
  );
}

export function PassportPage() {
  const { animalId = "" } = useParams();
  const { data: passport, isPending, error, refetch, isRefetching } = usePassport(animalId);

  if (toApiError(error)?.code === "NOT_FOUND" || toApiError(error)?.status === 404) return <NotFoundPage />;

  if (isPending) {
    return (
      <Page>
        <LoadingRegion label="Loading the passport">
          <div className="flex flex-col gap-6">
            <Skeleton height="64px" width="320px" />
            <div className="grid gap-4 sm:grid-cols-3">
              <Skeleton height="180px" />
              <Skeleton height="180px" />
              <Skeleton height="180px" />
            </div>
            <Skeleton lines={4} />
          </div>
        </LoadingRegion>
      </Page>
    );
  }
  if (error || !passport) {
    return (
      <Page>
        <PageHeader title="Passport" meta={<Mono>{animalId}</Mono>} />
        <ErrorNotice error={error} title="This passport couldn't load" onRetry={() => void refetch()} retrying={isRefetching} />
      </Page>
    );
  }

  const { animal } = passport;
  const pending = animal.identity_status !== "confirmed";

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col tab:flex-row">
      <div className="min-w-0 flex-1 px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8">
        <PageHeader
          lead={<EarTag animalId={animal.id} state={tagStateFor(animal.identity_status)} size="md" />}
          title={animal.name}
          meta={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span>
                <Mono className="text-ink">{animal.id}</Mono> · {animal.breed} · {sexWord(animal.sex)}
              </span>
              <span className="inline-flex items-center gap-2" title={animal.health.reason}>
                <StatusPill {...healthPill(animal.health.status)} />
                <span className="sr-only">{animal.health.reason}</span>
              </span>
            </span>
          }
          actions={
            <>
              <AgentLink animal={animal} />
              <ButtonLink to={`/audit?animal=${animal.id}`} variant="secondary">
                Audit trail
              </ButtonLink>
            </>
          }
        />
        {pending && (
          <div role="alert" className="mb-8 flex items-start gap-3 rounded-control border-2 border-uncertain bg-uncertain-soft p-4">
            <TriangleAlert aria-hidden="true" className="mt-0.5 size-5 flex-none text-uncertain-ink" strokeWidth={2.25} />
            <p className="font-bold">Identity not confirmed — financial actions are blocked until review.</p>
          </div>
        )}
        <IdentitySection passport={passport} />
        <EstimatesSection passport={passport} />
        <ValuationSection passport={passport} />
        <DocumentsSection passport={passport} />
        <CoverageSection passport={passport} />
        <LocationSection passport={passport} />
        <AlertsSection passport={passport} />
        <ClaimsSection passport={passport} />
        <div className="h-12" />
        <AwaitingBar passport={passport} />
      </div>
      <aside
        id="passbook"
        aria-label="Passbook"
        className="scroll-mt-(--shell-height) border-t-2 border-ink tab:sticky tab:top-16 tab:flex tab:h-[calc(100dvh-4rem-var(--tabbar-height))] lg:top-(--shell-height) lg:h-[calc(100dvh-var(--shell-height))] tab:w-(--passbook-width) tab:flex-none tab:flex-col tab:border-t-0 tab:border-l-2"
      >
        <AnimalPassbook animalId={animal.id} headingLevel={2} stickTo="window" className="tab:h-full" />
      </aside>
    </div>
  );
}
