import type { Replay, ScenarioTrack, Track } from "./api";
import { matchTime } from "./interpolate";

export type TrackIdentity =
  | { status: "associated"; animalId: string; name: string }
  | { status: "uncertain"; animalId: string | null; name: string | null }
  | { status: "unassigned" };

/** What `identityAt` needs to place the server's evidence on the replay clock. */
export interface IdentityContext {
  /** The replay's `anchor_at` in ms: observation time of scenario t = 0. */
  anchorMs?: number | null;
  /** Animal names by id, for the identity a track carried before it was released. */
  names?: ReadonlyMap<string, string>;
}

type Evidence = Record<string, unknown>;

export function identityContext(replay: Replay | undefined, animals: readonly { id: string; name: string }[]): IdentityContext {
  return {
    anchorMs: replay?.anchor_at ? Date.parse(replay.anchor_at) : null,
    names: new Map(animals.map((a) => [a.id, a.name])),
  };
}

/** An evidence timestamp as replay time, or null without one or without the replay's anchor. */
export function evidenceTime(value: unknown, anchorMs: number | null | undefined): number | null {
  if (typeof value !== "string" || anchorMs === null || anchorMs === undefined) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? (ms - anchorMs) / 1000 : null;
}

function lostTime(track: ScenarioTrack | undefined): number | null {
  return track?.events.find((e) => e.type === "track_lost")?.t ?? null;
}

/**
 * A track's identity as the overlay shows it at replay time `t`. The server's track carries where the
 * association ended up and the evidence of when: a matched or scan-zone track reads as unassigned until that
 * moment, and a track whose identity was released (lost, crowded, or by the continuity policy) carries its
 * earlier identity only until the release. The replay shows identity arriving and leaving rather than knowing it
 * in advance.
 */
export function identityAt(
  scenarioTrack: ScenarioTrack | undefined,
  server: Track | undefined,
  t: number,
  context: IdentityContext = {},
): TrackIdentity {
  if (!server || server.association_status === "unassigned") return { status: "unassigned" };
  const evidence = (server.association_evidence ?? {}) as Evidence;
  const anchor = context.anchorMs;

  if (server.association_status === "associated") {
    if (!server.animal_id) return { status: "unassigned" };
    if (server.association_method === "muzzle_match" || server.association_method === "zone_handoff") {
      const from =
        evidenceTime(evidence.observed_at, anchor) ?? (scenarioTrack ? matchTime(scenarioTrack.events) : null);
      if (from !== null && t < from - 1e-6) return { status: "unassigned" };
    }
    return { status: "associated", animalId: server.animal_id, name: server.animal_name ?? server.animal_id };
  }

  // Uncertain: from the moment the evidence names (a release, a crowded scan, a lost track).
  const since =
    evidence.event === "continuity"
      ? evidenceTime(evidence.released_at, anchor)
      : evidenceTime(evidence.observed_at, anchor) ?? lostTime(scenarioTrack);
  if (since !== null && t < since - 1e-6) {
    const previous = typeof evidence.previous_animal_id === "string" ? evidence.previous_animal_id : null;
    const earlier = (evidence.previous ?? {}) as Evidence;
    const from =
      evidenceTime(earlier.observed_at, anchor) ?? (scenarioTrack ? matchTime(scenarioTrack.events) : null);
    if (previous && (from === null || t >= from - 1e-6)) {
      return { status: "associated", animalId: previous, name: context.names?.get(previous) ?? previous };
    }
    return { status: "unassigned" };
  }
  return { status: "uncertain", animalId: server.animal_id, name: server.animal_name };
}

/** How the track got (or did not get) its identity, as of replay time `t`; null when there is nothing to say. */
export function associationNote(track: Track, t: number, context: IdentityContext = {}): string | null {
  const evidence = (track.association_evidence ?? {}) as Evidence;
  const at = evidenceTime(evidence.observed_at, context.anchorMs);
  const reached = at === null || t >= at - 1e-6;
  const inZone = typeof evidence.tracks_in_zone === "number" ? evidence.tracks_in_zone : null;

  if (evidence.event === "continuity") {
    const releasedAt = evidenceTime(evidence.released_at, context.anchorMs);
    if (releasedAt !== null && t < releasedAt - 1e-6) {
      const before: Track = {
        ...track,
        association_status: "associated",
        association_method: typeof evidence.previous_method === "string" ? evidence.previous_method : null,
        association_evidence: (evidence.previous ?? null) as Track["association_evidence"],
      };
      return associationNote(before, t, context);
    }
    return evidence.reason === "overlap"
      ? "Identity released · overlapped another animal"
      : "Identity released · out of view for more than 1 s";
  }
  if (evidence.event === "zone_scan") {
    if (!reached) return "Scan zone · waiting for a scan";
    if (evidence.reason === "multiple_tracks_in_zone") return `${inZone ?? "Several"} animals in zone — not identified`;
    if (track.association_method === "zone_handoff") {
      const inliers = typeof evidence.inliers === "number" ? evidence.inliers : null;
      return inliers !== null ? `Identified in scan zone · ${inliers} points` : "Identified in scan zone";
    }
    if (evidence.decision === "rejected") {
      return evidence.reason === "candidate_not_registered" || evidence.reason === "candidate_unconfirmed"
        ? "Scanned in zone · no registered animal matched"
        : "Scanned in zone · scan too weak to identify";
    }
  }
  if (track.association_method === "muzzle_match") {
    if (!reached) return "Muzzle match pending";
    const inliers = typeof evidence.inliers === "number" ? evidence.inliers : null;
    return inliers !== null ? `Muzzle match · ${inliers} verified points` : "Muzzle match";
  }
  if (track.association_method === "manual_review" || track.association_method === "human_review") {
    return track.association_status === "unassigned" ? "Unassigned by review" : "Assigned by review";
  }
  if (track.association_method) return track.association_method.replace(/_/g, " ");
  if (evidence.event === "track_lost") return "Lost behind an obstruction";
  return null;
}
