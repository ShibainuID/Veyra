import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill, Img, Sequence, staticFile, useVideoConfig } from "remotion";
import { useOffsetFrames } from "../lib/time";

// Live-action clips (the team's footage in public/footage). Each clip is placed at an absolute film time with a
// frame-accurate source offset; crops/push-ins are CSS transforms on a cover-fitted frame, grades are CSS filters.
export const CLIP = {
  hp: { src: "footage/hp.mp4", rev: "footage/hp_rev.mp4", dur: 8 },
  cctv: { src: "footage/cctv.mp4", rev: "footage/cctv_rev.mp4", dur: 8 },
  tracked: { src: "footage/cctv_tracked.mp4", rev: "footage/cctv_tracked.mp4", dur: 8 },
} as const;
export type ClipName = keyof typeof CLIP;

/** CSS crop/push: zoom about a focus point (fx, fy in 0..1 of the source frame) */
export type Frame = { zoom?: number; fx?: number; fy?: number; dx?: number; dy?: number };

const framing = ({ zoom = 1, fx = 0.5, fy = 0.5, dx = 0, dy = 0 }: Frame): React.CSSProperties => ({
  width: "100%",
  height: "100%",
  translate: dx || dy ? `${dx}px ${dy}px` : undefined,
  transformOrigin: `${fx * 100}% ${fy * 100}%`,
  scale: String(zoom),
});

export type Segment = {
  clip: ClipName;
  /** absolute film time the segment starts / ends (s) */
  start: number;
  end: number;
  /** source time at the segment start (s), on the forward clip */
  from: number;
  rate?: number;
  reverse?: boolean;
};

/** Ping-pong a short clip across [start, end): forward from `from` at `rate`, then backward, and so on. */
export function pingPong(clip: ClipName, start: number, end: number, from: number, rate: number, lo = 0, hi: number = CLIP[clip].dur - 0.05): Segment[] {
  const segs: Segment[] = [];
  let t = start,
    pos = from,
    fwd = true;
  while (t < end - 1e-3) {
    const room = fwd ? hi - pos : pos - lo;
    const len = Math.min(end - t, room / rate);
    if (len > 0.02) segs.push({ clip, start: t, end: t + len, from: pos, rate, reverse: !fwd });
    t += len;
    pos = fwd ? pos + len * rate : pos - len * rate;
    fwd = !fwd;
  }
  return segs;
}

export const Footage: React.FC<{
  segments: readonly Segment[];
  /** framing as a function of absolute time */
  frame?: Frame;
  filter?: string;
  style?: React.CSSProperties;
  name?: string;
}> = ({ segments, frame = {}, filter, style, name = "Footage" }) => {
  const { fps } = useVideoConfig();
  const off = useOffsetFrames();
  return (
    <AbsoluteFill style={{ overflow: "hidden", ...style }}>
      <AbsoluteFill style={{ ...framing(frame), filter }}>
        {segments.map((s, i) => {
          const c = CLIP[s.clip];
          const rate = s.rate ?? 1;
          // reversed clips: source position p on the forward clip is (dur - p) on the reversed copy
          const srcStart = s.reverse ? c.dur - s.from : s.from;
          const from = Math.round(s.start * fps);
          const dur = Math.max(1, Math.round(s.end * fps) - from);
          const rel = from - off;
          return (
            <Sequence key={i} name={`${name} ${i + 1}`} from={rel} durationInFrames={dur} premountFor={fps}>
              <Video
                src={staticFile(s.reverse ? c.rev : c.src)}
                trimBefore={Math.max(0, Math.round(srcStart * fps))}
                playbackRate={rate}
                muted
                objectFit="cover"
                style={{ width: "100%", height: "100%" }}
              />
            </Sequence>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Still: React.FC<{ src: string; frame?: Frame; filter?: string; style?: React.CSSProperties; fit?: "cover" | "contain" }> = ({
  src,
  frame = {},
  filter,
  style,
  fit = "cover",
}) => (
  <AbsoluteFill style={{ overflow: "hidden", ...style }}>
    <Img src={staticFile(src)} style={{ ...framing(frame), objectFit: fit, filter }} />
  </AbsoluteFill>
);

/** Keynote-style grade for live footage on the dark stage */
export const GRADE = {
  film: "contrast(1.08) saturate(0.92) brightness(0.86)",
  dark: "contrast(1.1) saturate(0.85) brightness(0.62)",
  cctv: "contrast(1.05) saturate(0.7) brightness(0.9)",
  backdrop: "blur(14px) brightness(0.42) saturate(0.8)",
} as const;
