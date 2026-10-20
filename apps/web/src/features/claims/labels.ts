import type { StatusTone } from "../../components/StatusPill";
import { humanize } from "../../lib/animal";

export const INCIDENT_KINDS = [
  { value: "accidental_injury", label: "Accidental injury" },
  { value: "death", label: "Death" },
  { value: "theft", label: "Theft" },
  { value: "illness", label: "Illness" },
] as const;

export type IncidentKind = (typeof INCIDENT_KINDS)[number]["value"];

export function incidentKindLabel(kind: string): string {
  return INCIDENT_KINDS.find((k) => k.value === kind)?.label ?? humanize(kind);
}

const CLAIM_STATUS: Record<string, { tone: StatusTone; label: string }> = {
  draft: { tone: "uncertain", label: "Evidence missing" },
  ready: { tone: "neutral", label: "Ready to submit" },
  assessment_pending: { tone: "awaiting", label: "Assessment pending" },
};

export function claimStatus(status: string): { tone: StatusTone; label: string } {
  return CLAIM_STATUS[status] ?? { tone: "neutral", label: humanize(status) };
}

export function isSubmitted(status: string): boolean {
  return status !== "draft" && status !== "ready";
}

export const CHECKLIST_LABEL: Record<string, string> = {
  identity_reference: "Passport muzzle reference",
  active_policy: "Active policy covering the incident",
  incident_facts: "Incident facts recorded",
  farmer_declaration: "Farmer declaration confirmed",
  observation_evidence: "Linked camera observation",
  vet_assessment: "Veterinary assessment",
  ownership_document: "Ownership document",
  vet_health_record: "Veterinary health record",
  identity_verified: "Muzzle re-scan matches the enrolled animal",
};

export function checklistLabel(key: string): string {
  return CHECKLIST_LABEL[key] ?? humanize(key);
}
