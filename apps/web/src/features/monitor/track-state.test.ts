import { describe, expect, it } from "vitest";
import type { ScenarioTrack, Track } from "./api";
import { associationNote, identityAt, type IdentityContext } from "./track-state";

const ANCHOR = "2026-10-20T09:00:00Z";
const context: IdentityContext = { anchorMs: Date.parse(ANCHOR), names: new Map([["animal-demo-001", "Sari"]]) };
const at = (s: number) => new Date(Date.parse(ANCHOR) + s * 1000).toISOString();
const scenarioTrack: ScenarioTrack = { track_key: "t-01", frames: [], events: [] };

function track(patch: Partial<Track>): Track {
  return {
    id: "trk-1",
    replay_id: "rpl-1",
    camera_id: "cam-pen-a",
    track_key: "t-01",
    animal_id: null,
    animal_name: null,
    association_status: "unassigned",
    association_method: null,
    association_evidence: null,
    first_seen: ANCHOR,
    last_seen: at(180),
    ...patch,
  };
}

const handedOver = track({
  animal_id: "animal-demo-001",
  animal_name: "Sari",
  association_status: "associated",
  association_method: "zone_handoff",
  association_evidence: { event: "zone_scan", observed_at: at(3), tracks_in_zone: 1, inliers: 31, quality: 0.88 },
});

describe("identityAt", () => {
  it("shows a scan-zone identity only from the scan on", () => {
    expect(identityAt(scenarioTrack, handedOver, 2.5, context).status).toBe("unassigned");
    expect(identityAt(scenarioTrack, handedOver, 3, context)).toEqual({ status: "associated", animalId: "animal-demo-001", name: "Sari" });
  });

  it("keeps a released identity until the release, then shows it uncertain", () => {
    const released = track({
      association_status: "uncertain",
      association_evidence: {
        event: "continuity",
        reason: "overlap",
        released_at: at(40),
        previous_animal_id: "animal-demo-001",
        previous_method: "zone_handoff",
        previous: handedOver.association_evidence,
      },
    });
    expect(identityAt(scenarioTrack, released, 1, context).status).toBe("unassigned");
    expect(identityAt(scenarioTrack, released, 20, context)).toEqual({ status: "associated", animalId: "animal-demo-001", name: "Sari" });
    expect(identityAt(scenarioTrack, released, 40, context).status).toBe("uncertain");
    expect(associationNote(released, 20, context)).toBe("Identified in scan zone · 31 points");
    expect(associationNote(released, 41, context)).toBe("Identity released · overlapped another animal");
  });

  it("reads a crowded scan as unassigned before it and uncertain after, never as an animal", () => {
    const crowded = track({
      association_status: "uncertain",
      association_evidence: { event: "zone_scan", reason: "multiple_tracks_in_zone", observed_at: at(3), tracks_in_zone: 2, previous_animal_id: null },
    });
    expect(identityAt(scenarioTrack, crowded, 2, context).status).toBe("unassigned");
    expect(identityAt(scenarioTrack, crowded, 3, context).status).toBe("uncertain");
    expect(associationNote(crowded, 4, context)).toBe("2 animals in zone — not identified");
  });

  it("names a scan that matched no registered animal", () => {
    const rejected = track({
      association_evidence: { event: "zone_scan", decision: "rejected", reason: "candidate_not_registered", observed_at: at(4), tracks_in_zone: 1 },
    });
    expect(associationNote(rejected, 3, context)).toBe("Scan zone · waiting for a scan");
    expect(associationNote(rejected, 4, context)).toBe("Scanned in zone · no registered animal matched");
    expect(identityAt(scenarioTrack, rejected, 5, context).status).toBe("unassigned");
  });
});
