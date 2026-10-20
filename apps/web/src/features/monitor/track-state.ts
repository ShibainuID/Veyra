import type { ScenarioTrack, Track } from "./api";
import { matchTime } from "./interpolate";

export type TrackIdentity =
  | { status: "associated"; animalId: string; name: string }
  | { status: "uncertain"; animalId: string | null; name: string | null }
  | { status: "unassigned" };

/**
 * A track's identity as the overlay shows it at replay time `t`. The server's track carries where the
 * association ended up; a muzzle-matched track reads as unassigned until the match moment is reached, so the
 * replay shows the identity arriving rather than knowing it in advance.
 */
export function identityAt(scenarioTrack: ScenarioTrack | undefined, server: Track | undefined, t: number): TrackIdentity {
  if (!server || server.association_status === "unassigned") return { status: "unassigned" };
  if (scenarioTrack && server.association_method === "muzzle_match") {
    const matched = matchTime(scenarioTrack.events);
    if (matched !== null && t < matched) return { status: "unassigned" };
  }
  if (server.association_status === "uncertain") {
    return { status: "uncertain", animalId: server.animal_id, name: server.animal_name };
  }
  if (!server.animal_id) return { status: "unassigned" };
  return { status: "associated", animalId: server.animal_id, name: server.animal_name ?? server.animal_id };
}
