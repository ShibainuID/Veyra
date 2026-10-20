/**
 * Audit event titles in the passbook's vocabulary. The passbook gets its titles from the
 * server; the audit log formats raw events here with the same words, and falls back to the
 * event type in plain words so a new event never shows a blank row.
 */
import { actionTitle } from "../actions/types";
import { alertKindLabel, productName } from "../../lib/animal";

type Data = Record<string, unknown>;

const str = (value: unknown): string | null => (typeof value === "string" && value ? value : null);

function actionLabel(data: Data): string {
  const type = str(data.action_type);
  return type ? actionTitle(type) : "Action";
}

function product(data: Data): string {
  return productName(str(data.product_id)) ?? "policy";
}

const EXECUTED_WORDS: Record<string, string> = { succeeded: "sent", failed: "failed", unknown: "outcome unknown" };

const TITLES: Record<string, (data: Data) => string> = {
  "action.proposed": (d) => `${actionLabel(d)} prepared`,
  "action.approved": (d) => `${actionLabel(d)} approved`,
  "action.declined": (d) => `${actionLabel(d)} declined`,
  "action.cancelled": (d) => `${actionLabel(d)} cancelled`,
  "action.expired": (d) => `${actionLabel(d)} expired`,
  "action.executed": (d) => {
    const status = str(d.status) ?? "unknown";
    const word = d.action_type === "PREMIUM_PAYMENT" && status === "succeeded" ? "paid" : (EXECUTED_WORDS[status] ?? status);
    return `${actionLabel(d)} ${word}`;
  },
  "policy.activated": (d) => `Policy active · ${product(d)}`,
  "policy.activation_pending": (d) => `Activation pending · ${product(d)}`,
  "seed.policy_created": (d) => `Policy active · ${product(d)}`,
  "valuation.confirmed": () => "Valued",
  "enrollment.confirmed": (d) => (d.decision === "link_existing" ? "Enrollment linked to this animal" : "Enrolled from guided video"),
  "seed.enrollment_confirmed": () => "Enrolled from guided video",
  "animal.registered": () => "Registered in herd",
  "seed.animal_created": () => "Registered in herd",
  "animal.references_linked": () => "Reference frames added",
  "alert.created": (d) => {
    const kind = str(d.kind);
    if (kind === "observation_quality") return "Observation quality warning";
    return kind ? `Alert · ${alertKindLabel(kind).toLowerCase()}` : "Alert created";
  },
  "alert.acknowledged": () => "Alert acknowledged",
  "alert.resolved": () => "Alert resolved",
  "alert.note_added": (d) => (d.note_kind === "assessment" ? "Assessment note" : "Review note"),
  "track.associated": () => "Identified on camera",
  "track.lost": () => "Camera track lost",
  "track.unassigned": () => "Camera track unassigned",
  "incident.recorded": (d) => {
    const kind = str(d.kind);
    return kind ? `Incident recorded · ${kind.replace(/_/g, " ")}` : "Incident recorded";
  },
  "incident.finding_added": (d) => (d.finding_type === "vet_assessment" ? "Vet assessment added" : "Vet health record added"),
  "claim.drafted": () => "Claim drafted",
  "claim.declaration_confirmed": () => "Farmer declaration confirmed",
  "claim.blocked": () => "Claim held · evidence incomplete",
  "claim.submitted": () => "Claim submitted · assessment pending",
  "demo.reset": () => "Demo reset",
};

/** `seed.policy_created` → "Policy created", `alert.created` → "Alert created". */
export function genericTitle(eventType: string): string {
  const parts = eventType.split(".");
  if (parts.length > 1 && parts[0] === "seed") parts.shift();
  const text = parts.join(" ").replace(/_/g, " ").trim();
  return text ? text[0]!.toUpperCase() + text.slice(1) : "Event";
}

export function eventTitle(eventType: string, data: Data = {}): string {
  const format = TITLES[eventType];
  return format ? format(data) : genericTitle(eventType);
}
