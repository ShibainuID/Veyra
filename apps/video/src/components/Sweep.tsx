import React from "react";
import { AbsoluteFill } from "remotion";
import { io, lerp, sm } from "../lib/h";

/** The reference's light-sweep wipe: a bright band crossing the frame left to right over [s0, s1]. */
export const Sweep: React.FC<{ t: number; s0: number; s1: number; strength?: number }> = ({ t, s0, s1, strength = 1 }) => {
  if (t < s0 || t > s1 + 0.05) return null;
  const bx = lerp(-260, 1280 + 260, io(sm(s0, s1, t)));
  return (
    <AbsoluteFill style={{ pointerEvents: "none", mixBlendMode: "screen" }}>
      <div
        style={{
          position: "absolute",
          left: bx - 260,
          top: 0,
          width: 380,
          height: 720,
          opacity: strength,
          background: "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.9) 70%, rgba(255,255,255,0.55) 85%, rgba(255,255,255,0) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

export const sweepX = (t: number, s0: number, s1: number) => lerp(-260, 1280 + 260, io(sm(s0, s1, t)));
