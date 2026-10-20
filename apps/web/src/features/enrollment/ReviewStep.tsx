import { CameraOff, CircleCheck, CircleMinus, Link2, Plus, RotateCcw, TriangleAlert, X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { Mono, Range } from "../../components/figures";
import { Provenance, type Source } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { cn } from "../../lib/cn";
import { identityReasonCopy, reviewReasons, type ReasonCopy } from "./review-copy";
import {
  REQUIRED_VIEWS,
  candidateTagState,
  missingViews,
  proposedCandidate,
  registersPending,
  type Decision,
  type Enrollment,
  type RequiredView,
  type ViewOut,
} from "./rules";

const SOURCES: readonly Source[] = ["live", "prototype", "simulated", "documented"];

export function toSource(value: unknown): Source {
  return SOURCES.includes(value as Source) ? (value as Source) : "simulated";
}

const VIEW_LABEL: Record<RequiredView, string> = { muzzle: "Muzzle", teeth: "Teeth", body: "Body" };
const CORNERS = ["tl", "tr", "br", "bl"] as const;

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * One registered 4:3 frame, the same scale and crop for all three views (the shared `.evidence-frame`).
 * The muzzle shows the crop the match used, since that box is exactly what the model saw.
 */
function ReviewFrame({ view, spec, source }: { view: RequiredView; spec: ViewOut | undefined; source: Source }) {
  const label = VIEW_LABEL[view];
  const crop = view === "muzzle" ? (spec?.crop_url ?? null) : null;
  const src = crop ?? spec?.url ?? null;
  const time = num(spec?.time_s);
  const sharpness = num(spec?.sharpness);
  const confidence = num(spec?.view_prob);
  return (
    <figure className="flex min-w-0 flex-col gap-3">
      <div className="evidence-frame" data-missing={src ? undefined : ""}>
        {src ? (
          <img src={src} alt={crop ? `${label} crop used for matching` : `${label} view`} decoding="async" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
            {spec ? (
              <CameraOff aria-hidden="true" className="size-8 text-muted" strokeWidth={2} />
            ) : (
              <TriangleAlert aria-hidden="true" className="size-8 text-uncertain" strokeWidth={2} />
            )}
            <p className="font-bold">{spec ? "No footage attached" : `No ${label.toLowerCase()} view found`}</p>
            <p className="text-sm text-muted">
              {spec ? "The time comes from the prepared sample; there is no frame to show." : "Retake, or confirm with a reason."}
            </p>
          </div>
        )}
        {crop && (
          <span className="crop-label rounded-control bg-shell/85 px-2 py-1 text-sm font-bold text-on-shell">
            Guide-box crop
          </span>
        )}
        {CORNERS.map((corner) => (
          <svg key={corner} className="reg-mark" data-corner={corner} viewBox="0 0 18 18" aria-hidden="true" focusable="false">
            <path d="M1.5 18V1.5H18" fill="none" stroke="currentColor" strokeWidth="3" />
          </svg>
        ))}
      </div>
      <figcaption className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span className="font-bold">{label}</span>
          {time !== null ? (
            <span className="text-sm text-muted">
              at <Mono>{time.toFixed(1)} s</Mono> in the video
            </span>
          ) : (
            <span className="text-sm text-muted">Not captured</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {sharpness !== null || confidence !== null ? (
            <span className="text-sm">
              {sharpness !== null && (
                <>
                  Sharpness <Mono className="font-bold">{sharpness.toFixed(0)}</Mono>
                </>
              )}
              {sharpness !== null && confidence !== null && <span className="text-muted"> · </span>}
              {confidence !== null && (
                <>
                  view match <Mono className="font-bold">{Math.round(confidence * 100)}%</Mono>
                </>
              )}
            </span>
          ) : (
            <span className="text-sm text-muted">{spec ? "Quality not measured" : "No frame"}</span>
          )}
          {spec && <Provenance source={source} />}
        </div>
      </figcaption>
    </figure>
  );
}

function CheckRow({ ok, tone, children }: { ok: boolean | null; tone?: "uncertain" | "danger"; children: ReactNode }) {
  const Icon: LucideIcon = ok === null ? CircleMinus : ok ? CircleCheck : TriangleAlert;
  return (
    <li className="flex gap-3 border-b border-line py-3">
      <Icon
        aria-hidden="true"
        className={cn(
          "mt-0.5 size-5 flex-none",
          ok === null ? "text-muted" : ok ? "text-ok" : tone === "danger" ? "text-danger" : "text-uncertain",
        )}
        strokeWidth={2.25}
      />
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

function ReasonRow({ reason }: { reason: ReasonCopy }) {
  return (
    <CheckRow ok={reason.tone === "neutral" ? null : false} tone={reason.tone === "danger" ? "danger" : "uncertain"}>
      <p className="font-bold">{reason.title}</p>
      {reason.detail && <p className="text-sm text-muted">{reason.detail}</p>}
    </CheckRow>
  );
}

function Checks({ enrollment }: { enrollment: Enrollment }) {
  const manifest = enrollment.manifest;
  const checks = (manifest?.checks ?? {}) as Record<string, unknown>;
  const missing = missingViews(enrollment);
  const views = manifest?.views ?? {};
  const cuts = Array.isArray(checks.scene_cuts_s) ? (checks.scene_cuts_s as unknown[]).filter((c) => typeof c === "number") : null;
  const times = REQUIRED_VIEWS.map((v) => num(views[v]?.time_s)).filter((t): t is number => t !== null);
  const inOrder = times.every((t, i) => i === 0 || t >= times[i - 1]!);
  const assignment = typeof checks.view_assignment === "string" ? checks.view_assignment : null;
  const reasons = reviewReasons(enrollment.review_reasons);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="mb-1 text-md font-bold">Checks</h3>
        <ul>
          <CheckRow ok={missing.length === 0}>
            <p className="font-bold">
              {missing.length === 0
                ? "All three required views present"
                : `Missing: ${missing.map((v) => VIEW_LABEL[v].toLowerCase()).join(", ")}`}
            </p>
          </CheckRow>
          <CheckRow ok={cuts === null ? null : cuts.length === 0}>
            <p className="font-bold">
              {cuts === null
                ? "Scene cuts not checked"
                : cuts.length === 0
                  ? "One continuous take, no cuts"
                  : `Cut at ${cuts.map((c) => `${(c as number).toFixed(1)} s`).join(", ")}`}
            </p>
            {cuts === null && <p className="text-sm text-muted">Cut detection didn&apos;t run for this enrollment, so check the video is one take.</p>}
          </CheckRow>
          <CheckRow ok={times.length < 2 ? null : inOrder}>
            <p className="font-bold">{inOrder ? "Views in the guided order" : "Views out of the guided order"}</p>
            <p className="text-sm text-muted">
              Muzzle, teeth, then body
              {times.length > 0 && (
                <>
                  {" "}
                  · <Mono>{times.map((t) => `${t.toFixed(1)} s`).join(" → ")}</Mono>
                </>
              )}
            </p>
          </CheckRow>
          {assignment && (
            <CheckRow ok={assignment === "detected" ? true : null}>
              <p className="font-bold">
                {assignment === "sample_fixture"
                  ? "Views placed from the sample's timings"
                  : assignment === "even_split"
                    ? "Views placed by position in the video"
                    : `View assignment: ${assignment.replace(/_/g, " ")}`}
              </p>
            </CheckRow>
          )}
        </ul>
      </div>
      <div>
        <h3 className="mb-1 text-md font-bold">For review</h3>
        {reasons.length === 0 ? (
          <p className="py-3 text-muted">Nothing flagged for review.</p>
        ) : (
          <ul>
            {reasons.map((reason) => (
              <ReasonRow key={reason.code} reason={reason} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Estimates({ enrollment }: { enrollment: Enrollment }) {
  const estimates = (enrollment.estimates ?? {}) as Record<string, Record<string, unknown>>;
  const age = estimates.age ?? {};
  const weight = estimates.weight ?? {};
  const ageLow = num(age.range_low);
  const ageHigh = num(age.range_high);
  const kgLow = num(weight.range_low);
  const kgHigh = num(weight.range_high);
  const band = num(weight.band);
  const measurements = Array.isArray(weight.measurements) ? (weight.measurements as Record<string, unknown>[]) : [];
  const method =
    weight.path === "image_withers_height"
      ? "From the withers height in the side view"
      : weight.path === "tape_heart_girth"
        ? "From a tape heart-girth measurement"
        : typeof weight.path === "string"
          ? weight.path.replace(/_/g, " ")
          : null;
  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-md font-bold">Estimates</h3>
      <dl className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <dt className="text-sm font-bold text-muted">Age</dt>
          <dd className="text-lg font-bold">
            {ageLow !== null && ageHigh !== null ? <Range low={ageLow} high={ageHigh} unit="months" /> : "No estimate"}
          </dd>
          {typeof age.dentition_stage === "string" && <dd className="text-sm">{age.dentition_stage}</dd>}
          <dd className="flex flex-wrap items-center gap-2">
            <Provenance source={toSource(age.source ?? enrollment.sources?.age)} />
            {age.review_required === true && <StatusPill tone="uncertain" label="Review" />}
          </dd>
          {typeof age.fixture_note === "string" && <dd className="text-sm text-muted">{age.fixture_note}</dd>}
        </div>
        <div className="flex flex-col gap-1.5">
          <dt className="text-sm font-bold text-muted">Weight</dt>
          <dd className="text-lg font-bold">
            {kgLow !== null && kgHigh !== null ? <Range low={kgLow} high={kgHigh} unit="kg" /> : "No estimate"}
          </dd>
          {method && (
            <dd className="text-sm">
              {method}
              {band !== null && (
                <>
                  {" "}
                  · band <Mono>±{(band * 100).toFixed(1)}%</Mono>
                </>
              )}
            </dd>
          )}
          {measurements.map((m, i) => (
            <dd key={i} className="text-sm text-muted">
              {String(m.name ?? "measurement").replace(/_/g, " ")}{" "}
              <Mono className="text-ink">
                {String(m.value ?? "—")} {String(m.unit ?? "")}
              </Mono>
            </dd>
          ))}
          <dd className="flex flex-wrap items-center gap-2">
            <Provenance source={toSource(weight.source ?? enrollment.sources?.weight)} />
            {weight.review_required === true && <StatusPill tone="uncertain" label="Review" />}
          </dd>
        </div>
      </dl>
      <p className="text-sm text-muted">
        Indicative only. Nothing is valued here: you confirm the valuation inputs on the passport.
      </p>
    </div>
  );
}

export interface ReviewStepProps {
  enrollment: Enrollment;
  onDecide: (decision: Decision, linkTo: string | null) => void;
  onRetake: () => void;
  retaking?: boolean;
}

function IdentityPanel({ enrollment, onDecide, onRetake, retaking }: ReviewStepProps) {
  const identity = enrollment.identity;
  const candidate = proposedCandidate(identity);
  const source = toSource(identity?.source ?? enrollment.sources?.identity);
  const reason = identityReasonCopy(identity?.reason);
  const accept = num(identity?.accept_inliers);
  const pending = registersPending(enrollment);

  let body: ReactNode;
  let actions: ReactNode;
  if (!identity) {
    body = <p>No identity result came back. Retake the video, or register the animal with a reason.</p>;
    actions = (
      <Button variant="primary" icon={Plus} onClick={() => onDecide("register_new", null)}>
        Register with a reason
      </Button>
    );
  } else if (candidate) {
    const name = candidate.animal_name ?? candidate.animal_id;
    body = (
      <>
        <StatusPill tone="uncertain" label="Possible duplicate" />
        <div className="flex items-center gap-4">
          <EarTag animalId={candidate.animal_id} state={candidateTagState(candidate)} size="md" />
          <div className="min-w-0">
            <p className="text-md font-bold">{name}</p>
            <p className="figures text-sm text-muted">{candidate.animal_id}</p>
          </div>
        </div>
        <p>
          This muzzle matches {name}, already on the farm:{" "}
          <Mono className="font-bold">{num(candidate.inliers) ?? "—"}</Mono> verified points
          {accept !== null && <> (a match needs more than {accept})</>}, similarity{" "}
          <Mono className="font-bold">{num(candidate.cosine)?.toFixed(2) ?? "—"}</Mono>.
        </p>
      </>
    );
    actions = (
      <>
        <Button variant="primary" icon={Link2} onClick={() => onDecide("link_existing", candidate.animal_id)}>
          Link to {name}
        </Button>
        <Button variant="secondary" icon={Plus} onClick={() => onDecide("register_new", null)}>
          Register as new, with a reason
        </Button>
      </>
    );
  } else if (identity.outcome === "new") {
    const closest = identity.candidates[0];
    body = (
      <>
        <StatusPill tone="ok" label="No match on the farm" />
        <p>{reason ?? "No animal on the farm matches this muzzle."}</p>
        {closest && (
          <p className="text-sm text-muted">
            Closest: {closest.animal_name ?? closest.animal_id} (<Mono>{closest.animal_id}</Mono>),{" "}
            <Mono>{num(closest.inliers) ?? "—"}</Mono> verified points
            {accept !== null && <>, below the {accept} a match needs</>}.
          </p>
        )}
      </>
    );
    actions = (
      <Button variant="primary" icon={Plus} onClick={() => onDecide("register_new", null)}>
        Register as a new animal
      </Button>
    );
  } else {
    body = (
      <>
        <StatusPill tone="uncertain" label="Identity uncertain" />
        <p>{reason ?? "The muzzle evidence is too weak to match or clear."}</p>
        <p className="text-sm">
          If you register it now, it needs a reason and stays <strong>pending review</strong>: no application, payment, or
          claim can be prepared until its identity is confirmed.
        </p>
      </>
    );
    actions = (
      <>
        <Button variant="primary" icon={RotateCcw} onClick={onRetake} loading={retaking} loadingLabel="Starting again…">
          Retake the video
        </Button>
        <Button variant="secondary" icon={Plus} onClick={() => onDecide("register_new", null)}>
          Register as pending, with a reason
        </Button>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-panel border-2 border-ink p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-md font-bold">Identity</h3>
        <span className="flex items-center gap-2">
          {identity?.method_version && <Mono className="text-sm text-muted">{identity.method_version}</Mono>}
          <Provenance source={source} />
        </span>
      </div>
      {body}
      {pending && candidate === null && identity?.outcome !== "uncertain" && (
        <p className="text-sm text-uncertain-ink">Without a muzzle view, a new animal stays pending review.</p>
      )}
      <div className="mt-1 flex flex-wrap gap-3">{actions}</div>
      <div className="border-t border-line pt-3">
        <Button variant="ghost" icon={X} onClick={() => onDecide("reject", null)} className="-ml-3 text-danger">
          Reject this enrollment
        </Button>
      </div>
    </div>
  );
}

export function ReviewStep(props: ReviewStepProps) {
  const { enrollment } = props;
  const views = enrollment.manifest?.views ?? {};
  const viewSource = toSource(enrollment.sources?.views ?? enrollment.manifest?.source);
  return (
    <div className="flex flex-col gap-10">
      <section aria-label="Evidence frames" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold">What VEYRA found</h2>
          <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
            Views <Provenance source={viewSource} /> · identity <Provenance source={toSource(enrollment.sources?.identity)} />
            {enrollment.processing_mode && (
              <>
                · mode <Mono className="text-ink">{enrollment.processing_mode}</Mono>
              </>
            )}
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {REQUIRED_VIEWS.map((view) => (
            <ReviewFrame key={view} view={view} spec={views[view]} source={viewSource} />
          ))}
        </div>
      </section>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-12">
        <div className="flex min-w-0 flex-col gap-10">
          <IdentityPanel {...props} />
          <Estimates enrollment={enrollment} />
        </div>
        <div className="min-w-0">
          <Checks enrollment={enrollment} />
        </div>
      </div>
    </div>
  );
}
