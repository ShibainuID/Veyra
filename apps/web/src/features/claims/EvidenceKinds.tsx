import { Cctv, Megaphone, NotebookPen, Stethoscope, type LucideIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { ErrorNotice } from "../../components/feedback";
import { Money, Mono, Timestamp } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { alertKindLabel, asSource, humanize } from "../../lib/animal";
import { cn } from "../../lib/cn";
import type { Role } from "../../lib/role-store";
import type { AgentAction } from "../actions";
import { approvalsHref, isOpen, latestAction } from "../finance/actions";
import { useProposeAction, type Alert, type Incident } from "../finance/api";
import { useAddFinding } from "./api";
import { FIELD } from "./IncidentForm";
import { incidentKindLabel } from "./labels";

/**
 * One kind of evidence, with who it comes from. The three kinds (farmer-reported, professional,
 * observed) each carry their own icon, label, and frame so they never blur together.
 */
function EvidenceBlock({
  id,
  icon: Icon,
  label,
  source,
  tone,
  children,
}: {
  id?: string;
  icon: LucideIcon;
  label: string;
  source: string;
  tone: "farmer" | "vet" | "system";
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn(
        "rounded-panel border-2 p-5",
        tone === "farmer" && "border-ink",
        tone === "vet" && "border-ink bg-surface",
        tone === "system" && "border-dashed border-line-strong",
      )}
    >
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-pill px-3 text-sm font-bold",
            tone === "farmer" && "bg-ink text-white",
            tone === "vet" && "border-2 border-ink text-ink",
            tone === "system" && "border-2 border-dashed border-muted text-muted",
          )}
        >
          <Icon aria-hidden="true" className="size-4" strokeWidth={2.25} />
          {label}
        </span>
        <h3 id={headingId} className="text-base font-bold">
          {source}
        </h3>
      </div>
      {children}
    </section>
  );
}

export function FarmerReport({ incident }: { incident: Incident }) {
  const facts = Object.entries(incident.facts ?? {});
  return (
    <EvidenceBlock icon={NotebookPen} label="Farmer-reported" source="What the farm recorded" tone="farmer">
      <dl className="grid grid-cols-1 gap-x-5 gap-y-1 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-y-2.5 [&>dd]:mb-2 sm:[&>dd]:mb-0">
        <dt className="text-sm text-muted">What happened</dt>
        <dd className="font-bold">{incidentKindLabel(incident.kind)}</dd>
        <dt className="text-sm text-muted">When</dt>
        <dd>
          <Timestamp value={incident.occurred_at} mode="absolute" />{" "}
          <span className="text-muted">
            · <Timestamp value={incident.occurred_at} mode="relative" />
          </span>
        </dd>
        <dt className="text-sm text-muted">Description</dt>
        <dd className="max-w-[65ch]">{incident.description}</dd>
        <dt className="text-sm text-muted">Estimated loss</dt>
        <dd>
          <Money minor={incident.estimated_loss_minor} currency={incident.currency} className="font-bold" />{" "}
          <span className="text-sm text-muted">the farm's estimate</span>
        </dd>
        {facts.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-sm text-muted">{humanize(key)}</dt>
            <dd className="mb-2 sm:mb-0">{typeof value === "string" ? value : JSON.stringify(value)}</dd>
          </div>
        ))}
        <dt className="text-sm text-muted">Recorded</dt>
        <dd className="text-sm">
          by <Mono>{incident.reported_by}</Mono> · <Mono>{incident.id}</Mono>
        </dd>
      </dl>
    </EvidenceBlock>
  );
}

interface Finding {
  id?: string;
  finding_type?: string;
  summary?: string;
  author_name?: string;
  author_role?: string;
  at?: string;
}

export function ProfessionalFindings({
  incident,
  role,
  needs,
  locked,
}: {
  incident: Incident;
  role: Role;
  /** Finding types the claim terms still need. */
  needs: ("vet_assessment" | "vet_health_record")[];
  locked: boolean;
}) {
  const findings = (incident.professional_findings ?? []) as Finding[];
  const canAdd = (role === "vet" || role === "manager") && !locked;
  return (
    <EvidenceBlock id="assessment" icon={Stethoscope} label="Professional" source="What a veterinarian assessed" tone="vet">
      {findings.length === 0 ? (
        <p className="text-muted">No professional finding yet. A vet's assessment is separate from the farm's report.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {findings.map((f, i) => (
            <li key={f.id ?? i} className="flex flex-col gap-1 border-t border-line pt-3 first:border-t-0 first:pt-0">
              <p className="text-sm font-bold">{f.finding_type === "vet_health_record" ? "Vet health record" : "Vet assessment"}</p>
              <p className="max-w-[65ch]">{f.summary}</p>
              <p className="text-sm text-muted">
                {f.author_name ?? "Unknown author"}
                {f.author_role && <> · {humanize(f.author_role)}</>}
                {f.at && (
                  <>
                    {" "}
                    · <Timestamp value={f.at} mode="absolute" />
                  </>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
      {canAdd ? (
        <FindingForm incidentId={incident.id} needs={needs} />
      ) : (
        !locked && (
          <p className="mt-4 text-sm text-muted">Only a vet or a manager adds professional findings. Switch role to Vet to add one.</p>
        )
      )}
    </EvidenceBlock>
  );
}

function FindingForm({ incidentId, needs }: { incidentId: string; needs: ("vet_assessment" | "vet_health_record")[] }) {
  const summaryId = useId();
  const toast = useToast();
  const add = useAddFinding(incidentId);
  const [type, setType] = useState<"vet_assessment" | "vet_health_record">(needs[0] ?? "vet_assessment");
  const [summary, setSummary] = useState("");
  const [tried, setTried] = useState(false);
  const tooShort = summary.trim().length < 10;
  return (
    <form
      noValidate
      className="mt-5 flex flex-col gap-3 border-t-2 border-ink pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (tooShort) return;
        add.mutate(
          { summary: summary.trim(), finding_type: type },
          {
            onSuccess: () => {
              setSummary("");
              setTried(false);
              toast.show({ tone: "ok", title: type === "vet_assessment" ? "Assessment added" : "Health record added", body: "The evidence list is updated." });
            },
          },
        );
      }}
    >
      <fieldset className="flex flex-wrap gap-x-5 gap-y-2">
        <legend className="mb-2 font-bold">Add a professional finding</legend>
        {(["vet_assessment", "vet_health_record"] as const).map((value) => (
          <label key={value} className="flex min-h-11 cursor-pointer items-center gap-2">
            <input type="radio" name={`finding-${incidentId}`} checked={type === value} onChange={() => setType(value)} className="size-5 accent-[var(--ink)]" />
            {value === "vet_assessment" ? "Assessment of this incident" : "Health record"}
          </label>
        ))}
      </fieldset>
      <label htmlFor={summaryId} className="font-bold">
        Finding
      </label>
      <textarea
        id={summaryId}
        rows={3}
        className={FIELD}
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
        placeholder="Examined on site. Laceration to the left hind leg, consistent with an accidental injury."
      />
      {tried && tooShort && (
        <p role="alert" className="text-sm font-bold text-danger">
          Write the finding in at least a sentence.
        </p>
      )}
      {add.error ? <ErrorNotice error={add.error} /> : null}
      <div>
        <Button type="submit" variant="primary" icon={Stethoscope} loading={add.isPending} loadingLabel="Adding…">
          Add assessment
        </Button>
      </div>
    </form>
  );
}

export function ObservedAlerts({
  alertIds,
  alerts,
  actions,
  role,
  canNotify,
}: {
  alertIds: readonly string[];
  alerts: readonly Alert[] | undefined;
  actions: readonly AgentAction[] | undefined;
  role: Role;
  canNotify: boolean;
}) {
  const linked = alertIds.map((id) => ({ id, alert: alerts?.find((a) => a.id === id) }));
  return (
    <EvidenceBlock icon={Cctv} label="Observed" source="What the cameras recorded" tone="system">
      <p className="mb-4 text-sm text-muted">Movement observations from the cameras. They are not a diagnosis.</p>
      {linked.length === 0 ? (
        <p className="text-muted">No camera alert is linked to this incident.</p>
      ) : (
        <ul className="flex flex-col gap-5">
          {linked.map(({ id, alert }) => (
            <li key={id} className="flex flex-col gap-2 border-t border-line pt-4 first:border-t-0 first:pt-0">
              {alert ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold">{alertKindLabel(alert.kind)}</span>
                    <Provenance source={asSource(typeof alert.rule?.source === "string" ? alert.rule.source : undefined)} />
                    <span className="text-sm text-muted">· {alert.camera_name}</span>
                  </div>
                  <p className="max-w-[65ch]">{alert.summary}</p>
                  <p className="text-sm text-muted">
                    <Timestamp value={alert.window_start} mode="absolute" /> to <Timestamp value={alert.window_end} mode="absolute" /> ·{" "}
                    <Link to={`/alerts/${alert.id}`} className="figures">
                      {alert.id}
                    </Link>
                  </p>
                  {canNotify && <NotifyInsurer alert={alert} actions={actions} role={role} />}
                </>
              ) : (
                <Mono>{id}</Mono>
              )}
            </li>
          ))}
        </ul>
      )}
    </EvidenceBlock>
  );
}

/** INSURER_NOTIFICATION: the agent prepares a notice about this alert; a manager stamps it. */
export function NotifyInsurer({ alert, actions, role }: { alert: Alert; actions: readonly AgentAction[] | undefined; role: Role }) {
  const propose = useProposeAction();
  const toast = useToast();
  const latest = latestAction(actions, "INSURER_NOTIFICATION", alert.id);
  if (latest && isOpen(latest)) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill tone="awaiting" label="Notification awaiting your stamp" />
        <ButtonLink to={approvalsHref(latest.id)} variant="ghost">
          Review it
        </ButtonLink>
      </div>
    );
  }
  if (latest?.status === "succeeded") {
    return <StatusPill tone="ok" label="Sandbox Mutual notified" />;
  }
  return (
    <div className="flex flex-col items-start gap-2">
      {propose.error ? <ErrorNotice error={propose.error} /> : null}
      <Button
        variant="secondary"
        icon={Megaphone}
        disabled={role === "vet"}
        loading={propose.isPending}
        loadingLabel="Preparing…"
        onClick={() =>
          propose.mutate(
            { action_type: "INSURER_NOTIFICATION", alert_id: alert.id },
            { onSuccess: () => toast.show({ tone: "ok", title: "Notification prepared — awaiting your stamp", body: "Nothing reaches the insurer until a manager stamps it." }) },
          )
        }
      >
        Notify insurer about this alert
      </Button>
    </div>
  );
}
