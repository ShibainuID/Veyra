import type { components } from "../../lib/api-types";
import type { StatusTone } from "../../components/StatusPill";

export type AlertView = components["schemas"]["AlertView"];
export type AlertStatus = AlertView["status"];

export const KIND_LABEL: Record<AlertView["kind"], string> = {
  reduced_movement: "Reduced movement",
  observation_quality: "Observation quality",
};

export const STATUS_LABEL: Record<AlertStatus, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

export const STATUS_TONE: Record<AlertStatus, StatusTone> = {
  open: "uncertain",
  acknowledged: "neutral",
  resolved: "ok",
};

export function alertSubject(alert: Pick<AlertView, "animal_name" | "animal_id" | "track_key">): string {
  if (alert.animal_id) return alert.animal_name ?? alert.animal_id;
  return alert.track_key ? `Unassigned track ${alert.track_key}` : "Unassigned track";
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export interface Comparison {
  /** What the bars measure, in words. */
  measure: string;
  bars: { label: string; value: number; display: string; tone: "ink" | "muted" | "alert" }[];
  /** Where the rule trips, on the same scale, with its label. */
  line: { value: number; label: string } | null;
  max: number;
}

/**
 * The bar comparison in the alert drawer, read from the rule the server recorded. Reduced movement compares this
 * window's tracked speed with the animal's earlier window; observation quality compares mean visibility with
 * the minimum the movement rule needs.
 */
export function comparison(alert: AlertView): Comparison | null {
  const rule = alert.rule as Record<string, unknown>;
  if (alert.kind === "reduced_movement") {
    const speed = num(rule.speed);
    const baseline = num(rule.baseline);
    const threshold = num(rule.threshold);
    if (speed === null || baseline === null || baseline <= 0) return null;
    const pct = (v: number) => `${Math.round((v / baseline) * 100)}%`;
    return {
      measure: "Tracked movement, as a share of the earlier window",
      bars: [
        { label: "Earlier window (baseline)", value: baseline, display: "100%", tone: "muted" },
        { label: "This window", value: speed, display: pct(speed), tone: "alert" },
      ],
      line:
        threshold !== null
          ? { value: baseline * (1 - threshold), label: `Alert below ${Math.round((1 - threshold) * 100)}% of baseline` }
          : null,
      max: Math.max(baseline, speed),
    };
  }
  const visibility = num(rule.mean_visibility) ?? num(rule.score);
  const minimum = num(rule.threshold);
  if (visibility === null) return null;
  return {
    measure: "Mean visibility of the track in the window",
    bars: [{ label: "This window", value: visibility, display: `${Math.round(visibility * 100)}%`, tone: "alert" }],
    line: minimum !== null ? { value: minimum, label: `Needs at least ${Math.round(minimum * 100)}%` } : null,
    max: 1,
  };
}

export interface AlertNote {
  author: string;
  authorName: string;
  role: string;
  at: string;
  text: string;
  kind: "assessment" | "review";
}

export function alertNotes(alert: AlertView): AlertNote[] {
  return (alert.notes ?? [])
    .map((n) => {
      const note = n as Record<string, unknown>;
      return {
        author: String(note.author ?? ""),
        authorName: String(note.author_name ?? note.author ?? "Someone"),
        role: String(note.role ?? ""),
        at: String(note.at ?? alert.updated_at),
        text: String(note.text ?? ""),
        kind: note.kind === "assessment" || note.role === "vet" ? ("assessment" as const) : ("review" as const),
      };
    })
    .filter((n) => n.text);
}

export function ruleName(alert: AlertView): string | null {
  const name = (alert.rule as Record<string, unknown>).name;
  return typeof name === "string" ? name : null;
}
