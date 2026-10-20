/**
 * The camera overlay's geometry: where each scenario track's box is at replay time `t`, and the replay clock
 * the overlay runs on. Boxes are `[x, y, w, h]`, normalized 0–1 to the camera frame, top-left origin
 * (services/api/domain/movement.py).
 */

export type Box = readonly [number, number, number, number];

export interface Frame {
  t: number;
  bbox: readonly number[];
  visibility: number;
}

export interface TrackEvent {
  t: number;
  type: "muzzle_match" | "track_lost";
}

/** Gaps longer than this between frames are treated as the track being away, not as motion. */
export const MAX_GAP_S = 2;

function toBox(bbox: readonly number[]): Box {
  return [bbox[0] ?? 0, bbox[1] ?? 0, bbox[2] ?? 0, bbox[3] ?? 0];
}

const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/**
 * The box at `t`, linearly interpolated between the two frames around it. Before the first frame, after the
 * track was lost, or past the last frame by more than one frame interval, there is no box.
 */
export function boxAt(frames: readonly Frame[], t: number, events: readonly TrackEvent[] = []): Box | null {
  if (frames.length === 0) return null;
  const lost = events.find((e) => e.type === "track_lost");
  if (lost && t >= lost.t) return null;
  const first = frames[0]!;
  const last = frames[frames.length - 1]!;
  if (t < first.t) return null;
  const interval = frames.length > 1 ? frames[1]!.t - first.t : 0.5;
  if (t > last.t + interval) return null;
  if (t >= last.t) return toBox(last.bbox);

  // Binary search for the last frame at or before t.
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid]!.t <= t) lo = mid;
    else hi = mid - 1;
  }
  const a = frames[lo]!;
  const b = frames[lo + 1];
  if (!b || b.t - a.t > MAX_GAP_S) return toBox(a.bbox);
  const k = (t - a.t) / (b.t - a.t);
  return [
    lerp(a.bbox[0] ?? 0, b.bbox[0] ?? 0, k),
    lerp(a.bbox[1] ?? 0, b.bbox[1] ?? 0, k),
    lerp(a.bbox[2] ?? 0, b.bbox[2] ?? 0, k),
    lerp(a.bbox[3] ?? 0, b.bbox[3] ?? 0, k),
  ];
}

/** Whether a muzzle match happened in the `flashS` seconds of replay time up to `t`. */
export function matchFlashing(events: readonly TrackEvent[], t: number, flashS: number): boolean {
  return events.some((e) => e.type === "muzzle_match" && t >= e.t && t - e.t < flashS);
}

/** The first muzzle-match time, which is when the track's identity becomes known on screen. */
export function matchTime(events: readonly TrackEvent[]): number | null {
  const match = events.find((e) => e.type === "muzzle_match");
  return match ? match.t : null;
}

export interface ClockSample {
  /** `progress_s` from the last poll of `GET /replays/{id}`. */
  progressS: number;
  /** When that poll arrived (ms since epoch). */
  receivedAt: number;
  speed: number;
  durationS: number;
  status: "running" | "finished" | "failed" | "stopped";
}

/**
 * The replay time to draw at `now`. The server's `progress_s` is the authority; between polls the clock runs
 * on at the replay speed, but never more than `maxLeadS` simulated seconds ahead of the last report, so a
 * stalled replay does not run away. A replay that is no longer running sits at its last progress.
 */
export function replayTimeAt(sample: ClockSample, now: number, maxLeadS = 3): number {
  const { progressS, receivedAt, speed, durationS, status } = sample;
  if (status === "finished") return durationS;
  if (status !== "running" || speed <= 0) return Math.min(durationS, progressS);
  const ahead = Math.max(0, ((now - receivedAt) / 1000) * speed);
  return Math.min(durationS, progressS + Math.min(ahead, Math.max(maxLeadS, speed * 1.5)));
}

/**
 * Where a camera-frame point lands on the pen map: the camera's field of view is a box around the camera's map
 * position, in map units (the map is 1000 × 420, so 0.27 × 0.36 keeps the frame's 16:9).
 */
export const FIELD_OF_VIEW = { width: 0.27, height: 0.36 } as const;

export function toMapPoint(camera: { map_x: number; map_y: number }, box: Box): { x: number; y: number } {
  const cx = box[0] + box[2] / 2;
  const cy = box[1] + box[3] / 2;
  return {
    x: camera.map_x + (cx - 0.5) * FIELD_OF_VIEW.width,
    y: camera.map_y + (cy - 0.5) * FIELD_OF_VIEW.height,
  };
}
