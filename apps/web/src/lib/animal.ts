/** Shared wording for an animal's identity, sex, and estimates. */
import { Eye, EyeOff, Hourglass, Stethoscope, type LucideIcon } from "lucide-react";
import type { EarTagState } from "../components/EarTag";
import type { StatusTone } from "../components/StatusPill";
import type { Source } from "../components/Provenance";
import { formatRange } from "./format";

export function tagStateFor(identityStatus: string | null | undefined): EarTagState {
  if (identityStatus === "confirmed") return "confirmed";
  if (identityStatus === "pending_review" || identityStatus === "pending" || identityStatus === "uncertain") return "pending";
  return "none";
}

export function identityPill(identityStatus: string | null | undefined): { tone: StatusTone; label: string } {
  switch (identityStatus) {
    case "confirmed":
      return { tone: "ok", label: "Confirmed" };
    case "pending_review":
    case "pending":
      return { tone: "uncertain", label: "Needs review" };
    case "rejected":
      return { tone: "danger", label: "Rejected" };
    default:
      return { tone: "neutral", label: identityStatus ? humanize(identityStatus) : "Unknown" };
  }
}

export function coveragePill(status: string | null | undefined): { tone: StatusTone; label: string; shortLabel?: string } {
  if (status === "active") return { tone: "ok", label: "Active" };
  if (status === "pending") return { tone: "awaiting", label: "Pending" };
  return { tone: "danger", label: "Not covered", shortLabel: "None" };
}

export type HealthStatus =
  | "needs_inspection"
  | "under_review"
  | "observation_gap"
  | "veterinary_reviewed"
  | "normal"
  | "not_monitored";

type HealthPill = { tone: StatusTone; label: string; shortLabel?: string; icon?: LucideIcon };

const HEALTH_PILL: Record<HealthStatus, HealthPill> = {
  needs_inspection: { tone: "danger", label: "Needs inspection", shortLabel: "Inspect", icon: Eye },
  under_review: { tone: "uncertain", label: "Under review", shortLabel: "Review", icon: Hourglass },
  observation_gap: { tone: "uncertain", label: "Observation gap", shortLabel: "Gap", icon: EyeOff },
  veterinary_reviewed: { tone: "ok", label: "Vet reviewed", shortLabel: "Vetted", icon: Stethoscope },
  normal: { tone: "ok", label: "Normal" },
  not_monitored: { tone: "neutral", label: "Not monitored", shortLabel: "None" },
};

/** A monitoring state from records, never a diagnosis: icon plus plain words. */
export function healthPill(status: HealthStatus | null | undefined): HealthPill {
  return HEALTH_PILL[status ?? "not_monitored"] ?? HEALTH_PILL.not_monitored;
}

export function sexWord(sex: string | null | undefined): string {
  if (sex === "F") return "Female";
  if (sex === "M") return "Male";
  return sex ?? "Sex unknown";
}

export interface RangeLike {
  range_low: number | null;
  range_high: number | null;
  unit: string;
  source?: string;
}

/** "24–30 months"; null when the estimate has no range. */
export function rangeText(range: RangeLike | null | undefined): string | null {
  if (!range || range.range_low == null || range.range_high == null) return null;
  return formatRange(range.range_low, range.range_high, range.unit === "months" ? "mo" : range.unit);
}

const SOURCES = new Set<Source>(["live", "prototype", "simulated", "documented"]);

/** Narrow an API `source` string to a provenance chip; unknown values read as simulated. */
export function asSource(source: string | null | undefined): Source {
  return source && SOURCES.has(source as Source) ? (source as Source) : "simulated";
}

export function humanize(value: string): string {
  const text = value.replace(/[_.]+/g, " ").trim();
  return text ? text[0]!.toUpperCase() + text.slice(1) : value;
}

const PRODUCT_NAMES: Record<string, string> = {
  "basic-mortality": "Basic Mortality & Accident",
  "mortality-theft": "Mortality + Theft",
  "dairy-health-plus": "Dairy Health Plus",
};

/** Sandbox product names (from the demo catalog); unknown IDs read in plain words. */
export function productName(productId: string | null | undefined): string | null {
  if (!productId) return null;
  return PRODUCT_NAMES[productId] ?? humanize(productId.replace(/-/g, " "));
}

const PROVIDER_NAMES: Record<string, string> = {
  "sandbox-insurer": "Sandbox Mutual",
  "sandbox-payment": "Sandbox payments",
};

/** Sandbox provider names, for stamps and policy lines; unknown IDs pass through. */
export function providerName(providerId: string | null | undefined): string | undefined {
  if (!providerId) return undefined;
  return PROVIDER_NAMES[providerId] ?? providerId;
}

/** Alert kinds in plain words. */
export function alertKindLabel(kind: string): string {
  if (kind === "reduced_movement") return "Reduced movement";
  if (kind === "observation_quality") return "Observation quality";
  return humanize(kind);
}
