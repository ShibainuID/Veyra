import React from "react";
import { AbsoluteFill } from "remotion";
import TRACKS from "../data/tracks.json";
import { Footage, Segment, GRADE } from "./Footage";
import { clamp, eo } from "../lib/h";
import { FONT } from "../theme";

// Barn CCTV with VEYRA's own overlays: detections from the recorded track data (demo/media/veo/out/tracks.json,
// yolov8x + botsort, 1920x1080), the calibrated scan zone, and the one track that is associated with a passport.
type Box = [string, number, number, number, number, number];
const FR = (TRACKS as unknown as { frames: [number, Box[]][] }).frames;
export const ASSOCIATED_TRACK = "11"; // Sari, handed over in the scan zone (run_report.json: link status confirmed)
export const SCAN_ZONE = { x0: 0.4781, y0: 0.6611, x1: 0.7021, y1: 0.8463 };

/** source-clip time shown at film time t, for a list of segments */
export function sourceTime(segs: readonly Segment[], t: number, dur = 8) {
  for (const s of segs) {
    if (t >= s.start && t < s.end) {
      const d = (t - s.start) * (s.rate ?? 1);
      return s.reverse ? s.from - d : s.from + d;
    }
  }
  const last = segs[segs.length - 1];
  return last ? Math.min(dur, last.from) : 0;
}

/** interpolated boxes at source time st (normalized 0..1) */
export function boxesAt(st: number) {
  let i = 0;
  while (i < FR.length - 2 && FR[i + 1][0] <= st) i++;
  const [ta, A] = FR[i];
  const [tb, Bx] = FR[Math.min(FR.length - 1, i + 1)];
  const u = tb > ta ? clamp((st - ta) / (tb - ta)) : 0;
  return A.map((a) => {
    const b = Bx.find((q) => q[0] === a[0]) ?? a;
    const l = (k: number) => (a[k] as number) + ((b[k] as number) - (a[k] as number)) * u;
    return { id: a[0], x0: l(1) / 1920, y0: l(2) / 1080, x1: l(3) / 1920, y1: l(4) / 1080 };
  });
}

export const CctvView: React.FC<{
  t: number;
  segments: readonly Segment[];
  /** show unassigned detections from this time */
  detectAt?: number;
  /** associate the scan-zone track with Sari from this time */
  assocAt?: number;
  zoneAt?: number;
  /** label scale (1 = full-frame 1280x720) */
  ui?: number;
  hud?: boolean;
  clock?: (t: number) => string;
  filter?: string;
  frame?: { zoom?: number; fx?: number; fy?: number };
  name?: string;
  highlightRed?: number; // turn the associated box orange (alert) from this time
}> = ({ t, segments, detectAt = Infinity, assocAt = Infinity, zoneAt = Infinity, ui = 1, hud = true, clock, filter = GRADE.cctv, frame = {}, name = "CCTV", highlightRed = Infinity }) => {
  const st = sourceTime(segments, t);
  const boxes = boxesAt(st);
  const det = eo((t - detectAt) / 0.6);
  const as = eo((t - assocAt) / 0.4);
  const zn = eo((t - zoneAt) / 0.5);
  const zoom = frame.zoom ?? 1,
    fx = frame.fx ?? 0.5,
    fy = frame.fy ?? 0.5;
  const alert = t >= highlightRed;
  const assocColor = alert ? "#ffb26b" : "oklch(0.86 0.17 92)";
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={{ transformOrigin: `${fx * 100}% ${fy * 100}%`, scale: String(zoom) }}>
        <Footage name={name} segments={segments} filter={filter} />
        <svg viewBox="0 0 1000 562.5" preserveAspectRatio="xMidYMid slice" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          {zn > 0 ? (
            <rect
              x={SCAN_ZONE.x0 * 1000}
              y={SCAN_ZONE.y0 * 562.5}
              width={(SCAN_ZONE.x1 - SCAN_ZONE.x0) * 1000}
              height={(SCAN_ZONE.y1 - SCAN_ZONE.y0) * 562.5}
              fill="none"
              stroke="oklch(0.86 0.17 92)"
              strokeWidth={2 / zoom}
              strokeDasharray={`${8 / zoom} ${6 / zoom}`}
              opacity={zn * 0.9}
            />
          ) : null}
          {boxes.map((b) => {
            const isA = b.id === ASSOCIATED_TRACK;
            const a = isA ? Math.max(det * (1 - as), as) : det * 0.75;
            if (a <= 0.01) return null;
            return (
              <rect
                key={b.id}
                x={b.x0 * 1000}
                y={b.y0 * 562.5}
                width={(b.x1 - b.x0) * 1000}
                height={(b.y1 - b.y0) * 562.5}
                rx={4 / zoom}
                fill="none"
                stroke={isA && as > 0 ? assocColor : "rgba(255,255,255,0.75)"}
                strokeWidth={(isA && as > 0 ? 3 : 1.4) / zoom}
                strokeDasharray={isA && as > 0 ? undefined : `${5 / zoom} ${4 / zoom}`}
                opacity={a}
              />
            );
          })}
        </svg>
        {/* the associated cow's tag label, attached to its box */}
        {as > 0
          ? (() => {
              const b = boxes.find((q) => q.id === ASSOCIATED_TRACK);
              if (!b) return null;
              return (
                <div
                  style={{
                    position: "absolute",
                    left: `${b.x0 * 100}%`,
                    top: `${b.y0 * 100}%`,
                    translate: "0 -100%",
                    scale: String(ui / zoom),
                    transformOrigin: "0 100%",
                    opacity: as,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 10px",
                    marginTop: -6,
                    borderRadius: 8,
                    background: assocColor,
                    color: "#111",
                    fontFamily: FONT.mono,
                    fontWeight: 700,
                    fontSize: 24,
                    whiteSpace: "nowrap",
                  }}
                >
                  001 · Sari
                </div>
              );
            })()
          : null}
      </AbsoluteFill>
      {hud ? (
        <>
          <div style={{ position: "absolute", left: 20 * ui, top: 18 * ui, display: "flex", alignItems: "center", gap: 10 * ui, fontFamily: FONT.mono, fontWeight: 700, fontSize: 28 * ui, color: "#fff", textShadow: "0 1px 3px rgba(0,0,0,0.8)" }}>
            <span style={{ width: 14 * ui, height: 14 * ui, borderRadius: 8 * ui, background: "#ff453a" }} />
            CAM-01 · Pen A · feed line
          </div>
          {clock ? (
            <div style={{ position: "absolute", right: 20 * ui, top: 18 * ui, fontFamily: FONT.mono, fontWeight: 700, fontSize: 28 * ui, color: "#fff", textShadow: "0 1px 3px rgba(0,0,0,0.8)" }}>{clock(t)}</div>
          ) : null}
        </>
      ) : null}
    </AbsoluteFill>
  );
};

/** HH:MM:SS clock for the recorded replay, mapped from the clip's source time */
export const replayClock = (segs: readonly Segment[], base = 17 * 3600 + 9 * 60 + 10) => (t: number) => {
  const s = Math.floor(base + sourceTime(segs, t));
  const hh = String(Math.floor(s / 3600)).padStart(2, "0"),
    mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0"),
    ss = String(s % 60).padStart(2, "0");
  return `20 OCT 2026 · ${hh}:${mm}:${ss}`;
};
