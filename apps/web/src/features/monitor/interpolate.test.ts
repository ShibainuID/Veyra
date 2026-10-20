import { describe, expect, it } from "vitest";
import { boxAt, matchFlashing, matchTime, replayTimeAt, toMapPoint, type Frame } from "./interpolate";

const frames: Frame[] = [
  { t: 0, bbox: [0.1, 0.2, 0.2, 0.1], visibility: 0.9 },
  { t: 0.5, bbox: [0.2, 0.4, 0.2, 0.1], visibility: 0.9 },
  { t: 1, bbox: [0.3, 0.4, 0.4, 0.3], visibility: 0.9 },
  // a gap: the track was away
  { t: 10, bbox: [0.8, 0.8, 0.1, 0.1], visibility: 0.5 },
];

describe("boxAt", () => {
  it("returns the frame's box exactly on a frame", () => {
    expect(boxAt(frames, 0.5)).toEqual([0.2, 0.4, 0.2, 0.1]);
  });

  it("interpolates linearly between neighbouring frames", () => {
    const box = boxAt(frames, 0.25)!;
    expect(box[0]).toBeCloseTo(0.15);
    expect(box[1]).toBeCloseTo(0.3);
    const late = boxAt(frames, 0.75)!;
    expect(late[2]).toBeCloseTo(0.3);
    expect(late[3]).toBeCloseTo(0.2);
  });

  it("holds the last box across a long gap instead of sliding through it", () => {
    expect(boxAt(frames, 5)).toEqual([0.3, 0.4, 0.4, 0.3]);
  });

  it("has no box before the track starts, or after it ends or is lost", () => {
    expect(boxAt(frames.slice(1), 0.2)).toBeNull();
    expect(boxAt(frames, 10.2)).toEqual([0.8, 0.8, 0.1, 0.1]);
    expect(boxAt(frames, 20)).toBeNull();
    expect(boxAt(frames, 0.75, [{ t: 0.7, type: "track_lost" }])).toBeNull();
    expect(boxAt([], 1)).toBeNull();
  });
});

describe("muzzle-match moments", () => {
  const events = [{ t: 4, type: "muzzle_match" as const }];
  it("flashes only just after the match", () => {
    expect(matchFlashing(events, 3.9, 1)).toBe(false);
    expect(matchFlashing(events, 4.2, 1)).toBe(true);
    expect(matchFlashing(events, 5.1, 1)).toBe(false);
    expect(matchTime(events)).toBe(4);
    expect(matchTime([])).toBeNull();
  });
});

describe("replayTimeAt", () => {
  const sample = { progressS: 40, receivedAt: 1_000, speed: 10, durationS: 180, status: "running" as const };

  it("runs on at the replay speed between polls", () => {
    expect(replayTimeAt(sample, 1_000)).toBe(40);
    expect(replayTimeAt(sample, 1_500)).toBe(45);
  });

  it("never runs far ahead of the last report, or past the end", () => {
    expect(replayTimeAt(sample, 60_000)).toBe(55);
    expect(replayTimeAt({ ...sample, progressS: 178 }, 3_000)).toBe(180);
  });

  it("sits at the end when finished and at the last progress when stopped", () => {
    expect(replayTimeAt({ ...sample, status: "finished" }, 2_000)).toBe(180);
    expect(replayTimeAt({ ...sample, status: "stopped" }, 9_000)).toBe(40);
  });
});

describe("toMapPoint", () => {
  it("places a box centre around its camera on the pen map", () => {
    expect(toMapPoint({ map_x: 0.5, map_y: 0.5 }, [0.4, 0.4, 0.2, 0.2])).toEqual({ x: 0.5, y: 0.5 });
    const right = toMapPoint({ map_x: 0.22, map_y: 0.3 }, [0.8, 0.4, 0.2, 0.2]);
    expect(right.x).toBeGreaterThan(0.22);
  });
});
