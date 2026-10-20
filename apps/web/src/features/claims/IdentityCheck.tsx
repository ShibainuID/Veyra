import { CircleCheck, CircleX, FlaskConical, ScanLine, TriangleAlert, Upload } from "lucide-react";
import { useRef } from "react";
import { Button } from "../../components/Button";
import { EvidenceFrame } from "../../components/EvidenceFrame";
import { ErrorNotice } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { StatusPill, type StatusTone } from "../../components/StatusPill";
import { cn } from "../../lib/cn";
import type { Role } from "../../lib/role-store";
import type { Claim } from "../finance/api";
import { SCAN_ACCEPT, useIdentityCheck, type IdentityCheck, type IdentitySample } from "./api";

const OUTCOME: Record<IdentityCheck["outcome"], { tone: StatusTone; label: string }> = {
  match: { tone: "ok", label: "Match" },
  mismatch: { tone: "danger", label: "Mismatch" },
  uncertain: { tone: "uncertain", label: "Uncertain" },
};

const INPUT_LABEL: Record<string, string> = { photo: "Photo scan", video: "Video scan", sample: "Demo sample" };

/** What the latest check means for submission, in one line with its icon. */
function Consequence({ check, animalName }: { check: IdentityCheck; animalName: string }) {
  if (check.outcome === "match") {
    return (
      <p className="flex items-start gap-2 font-bold text-ok">
        <CircleCheck aria-hidden="true" className="mt-0.5 size-5 flex-none" strokeWidth={2.25} />
        Identity verified: the checklist item is on file.
      </p>
    );
  }
  const mismatch = check.outcome === "mismatch";
  const Icon = mismatch ? CircleX : TriangleAlert;
  return (
    <p className={cn("flex items-start gap-2 font-bold", mismatch ? "text-danger" : "text-uncertain-ink")}>
      <Icon aria-hidden="true" className="mt-0.5 size-5 flex-none" strokeWidth={2.25} />
      <span>
        {mismatch ? "A mismatch blocks submission." : "An uncertain scan blocks submission."} The claim can't go to Sandbox Mutual until
        a re-scan matches {animalName}.
      </span>
    </p>
  );
}

function CheckResult({ check, animalName }: { check: IdentityCheck; animalName: string }) {
  const outcome = OUTCOME[check.outcome];
  const sample = check.input === "sample";
  const reference = check.reference;
  const headline =
    check.outcome === "match" ? `The scan matches the muzzle enrolled for ${animalName}.` : (check.reason ?? "The scan was not verified.");
  return (
    <div className="flex flex-col gap-4 rounded-panel border-2 border-ink p-5" data-outcome={check.outcome}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={outcome.tone} label={outcome.label} />
        <Provenance source={check.source} />
        <span className="text-sm text-muted">
          {INPUT_LABEL[check.input ?? ""] ?? "Scan"} · <Timestamp value={check.created_at} mode="relative" />
          {check.checked_by_name && <> · {check.checked_by_name}</>}
        </span>
      </div>
      <p className="text-md font-bold">{headline}</p>
      <div className="grid grid-cols-2 gap-3">
        <EvidenceFrame
          view="muzzle"
          caption="Enrolled muzzle"
          src={reference?.crop_url ?? reference?.frame_url ?? null}
          alt={`${animalName}, enrolled muzzle reference`}
          recorded={Boolean(reference)}
          missingNote={reference?.note ? `Reference on record: ${reference.note}.` : "No enrolled muzzle reference is on file."}
        />
        <EvidenceFrame
          view="muzzle"
          caption="Claim scan"
          src={check.scan.crop_url}
          alt="Muzzle scanned for this claim, cropped to the guide box"
          capturedAt={check.created_at}
          recorded
          missingNote={sample ? "Demo sample: there is no scan image, only a simulated outcome." : "No muzzle frame could be read from the scan."}
        />
      </div>
      <dl className="grid gap-x-6 sm:grid-cols-2">
        <div className="flex flex-col gap-1 border-t border-line py-2.5">
          <dt className="text-sm text-muted">Verified feature matches</dt>
          <dd>
            {check.inliers !== null ? <Mono className="font-bold">{check.inliers}</Mono> : <span className="text-muted">None</span>}{" "}
            <span className="text-sm text-muted">
              (more than <Mono>{check.accept_inliers}</Mono> needed)
            </span>
          </dd>
        </div>
        <div className="flex flex-col gap-1 border-t border-line py-2.5">
          <dt className="text-sm text-muted">Best match</dt>
          <dd>
            {check.matched_animal_id ? (
              <>
                {check.matched_animal_name ?? check.matched_animal_id} <Mono className="text-sm text-muted">{check.matched_animal_id}</Mono>
              </>
            ) : (
              <span className="text-muted">No enrolled animal verified</span>
            )}
          </dd>
        </div>
      </dl>
      <Consequence check={check} animalName={animalName} />
    </div>
  );
}

export interface IdentityCheckStepProps {
  claim: Claim;
  animalName: string;
  role: Role;
  /** The claim was submitted: show the record, offer no new scan. */
  locked: boolean;
}

/**
 * The anti-fraud step for a death claim: scan the dead animal's muzzle and compare it with the muzzle
 * enrolled on its passport. A mismatch or an uncertain scan keeps the claim from being submitted.
 */
export function IdentityCheckStep({ claim, animalName, role, locked }: IdentityCheckStepProps) {
  const check = useIdentityCheck(claim.id, claim.animal_id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [latest, ...earlier] = claim.identity_checks ?? [];
  const canScan = !locked && (role === "manager" || role === "operator");
  const running = check.isPending ? check.variables : undefined;
  const runningSample = (sample: IdentitySample) => Boolean(running && "sample" in running && running.sample === sample);
  const sample = (value: IdentitySample) => check.mutate({ sample: value });

  return (
    <div className="flex flex-col gap-5">
      {latest ? (
        <CheckResult check={latest} animalName={animalName} />
      ) : (
        <p className="rounded-panel border-2 border-dashed border-line-strong p-4 text-muted">
          No scan yet. A death claim can't be submitted until a muzzle re-scan matches {animalName}; a mismatch blocks submission.
        </p>
      )}

      {canScan ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted">
              Fill the frame with the muzzle, nose centred. VEYRA crops the same guide box as enrollment (90% of the width).
            </p>
            <input
              ref={fileRef}
              type="file"
              accept={SCAN_ACCEPT}
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) check.mutate({ file });
              }}
            />
            <div>
              <Button
                variant="primary"
                icon={latest ? ScanLine : Upload}
                loading={Boolean(running && "file" in running)}
                loadingLabel="Comparing…"
                disabled={check.isPending && !(running && "file" in running)}
                onClick={() => fileRef.current?.click()}
              >
                {latest ? "Scan again" : "Upload muzzle photo or video"}
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-3 rounded-control border-2 border-dashed border-line-strong p-4">
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
              <Provenance source="simulated" />
              No camera here? Run the check with a prepared outcome instead.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                variant="secondary"
                icon={FlaskConical}
                loading={runningSample("match")}
                loadingLabel="Checking…"
                disabled={check.isPending && !runningSample("match")}
                onClick={() => sample("match")}
              >
                Use sample: matching scan
              </Button>
              <Button
                variant="secondary"
                icon={FlaskConical}
                loading={runningSample("mismatch")}
                loadingLabel="Checking…"
                disabled={check.isPending && !runningSample("mismatch")}
                onClick={() => sample("mismatch")}
              >
                Use sample: wrong cow
              </Button>
            </div>
          </div>
        </div>
      ) : (
        !locked && <p className="text-muted">A manager or operator scans the muzzle.</p>
      )}
      {check.error ? <ErrorNotice error={check.error} title="The scan wasn't checked" /> : null}

      {earlier.length > 0 && (
        <div>
          <h3 className="mb-2 font-bold">Earlier scans</h3>
          <ul className="flex flex-col border-t border-line">
            {earlier.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line py-2.5">
                <span className="flex items-center gap-2">
                  <StatusPill tone={OUTCOME[c.outcome].tone} label={OUTCOME[c.outcome].label} />
                  <Provenance source={c.source} />
                </span>
                <Timestamp value={c.created_at} mode="absolute" className="text-sm text-muted" />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
