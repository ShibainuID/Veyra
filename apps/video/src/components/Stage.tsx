import React, { useLayoutEffect, useRef } from "react";
import { AbsoluteFill } from "remotion";
import { io, lerp, rng } from "../lib/h";
import { HEIGHT, WIDTH } from "../beats";

// Port of the reference's stage(): near-black keynote set, key-light gradient above the hero object,
// an elliptical floor pool of light under it and out-of-focus background bokeh. Drawn on a canvas every frame.
export type StageLight = {
  /** screen point of the floor under the hero object */
  cx: number;
  cy: number;
  /** object scale in px (the reference's c.unit) */
  unit: number;
  /** key light 0..1 */
  key: number;
  /** 0 = dark stage, 1 = pristine white stage (the tagline) */
  white?: number;
};

export function paintStage(x: CanvasRenderingContext2D, W: number, Hh: number, c: StageLight, t: number) {
  const k = c.key;
  x.save();
  x.globalAlpha = 1;
  x.fillStyle = "#030304";
  x.fillRect(0, 0, W, Hh);
  let g = x.createRadialGradient(c.cx, c.cy - c.unit * 0.9, 10, c.cx, c.cy - c.unit * 0.6, 820);
  g.addColorStop(0, `rgba(44,47,60,${0.9 * k})`);
  g.addColorStop(0.45, `rgba(20,21,28,${0.8 * k})`);
  g.addColorStop(1, "rgba(3,3,4,0)");
  x.fillStyle = g;
  x.fillRect(0, 0, W, Hh);
  // floor pool of light
  x.save();
  x.translate(c.cx, c.cy);
  x.scale(1, 0.24);
  g = x.createRadialGradient(0, 0, 0, 0, 0, c.unit * 2.6);
  g.addColorStop(0, `rgba(70,74,92,${0.42 * k})`);
  g.addColorStop(1, "rgba(70,74,92,0)");
  x.fillStyle = g;
  x.beginPath();
  x.arc(0, 0, c.unit * 2.6, 0, 7);
  x.fill();
  x.restore();
  // out-of-focus background bokeh (shallow depth of field)
  const r = rng(404);
  for (let i = 0; i < 6; i++) {
    const bx = r() * W + Math.sin(t * 0.2 + i) * 14 - (c.cx - 640) * 0.15,
      by = r.range(0.05, 0.5) * Hh,
      rad = r.range(40, 110),
      hue = r.pick(["120,110,255", "255,140,90", "90,200,255"]);
    const a = r.range(0.025, 0.05) * k;
    g = x.createRadialGradient(bx, by, 0, bx, by, rad);
    g.addColorStop(0, `rgba(${hue},${a})`);
    g.addColorStop(0.6, `rgba(${hue},${a * 0.6})`);
    g.addColorStop(1, `rgba(${hue},0)`);
    x.fillStyle = g;
    x.beginPath();
    x.arc(bx, by, rad, 0, 7);
    x.fill();
  }
  // white stage (the reference's L.white branch)
  const wv = c.white ?? 0;
  if (wv > 0) {
    // revealed by the light-sweep wipe (left to right), as in the reference's explainer()
    if (wv < 1) {
      x.beginPath();
      x.rect(0, 0, Math.max(0, lerp(-260, W + 260, io(wv))), Hh);
      x.clip();
    }
    x.fillStyle = "#e4e4e9";
    x.fillRect(0, 0, W, Hh);
    g = x.createRadialGradient(c.cx, c.cy - 220, 40, c.cx, c.cy - 120, 900);
    g.addColorStop(0, "#ffffff");
    g.addColorStop(0.55, "#f4f4f7");
    g.addColorStop(1, "#dcdce2");
    x.fillStyle = g;
    x.fillRect(0, 0, W, Hh);
  }
  x.restore();
}

export const Stage: React.FC<{ light: StageLight; t: number; opacity?: number }> = ({ light, t, opacity = 1 }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const { cx, cy, unit, key, white } = light;
  useLayoutEffect(() => {
    const x = ref.current?.getContext("2d");
    if (x) paintStage(x, WIDTH, HEIGHT, { cx, cy, unit, key, white }, t);
  }, [cx, cy, unit, key, white, t]);
  return (
    <AbsoluteFill style={{ opacity }}>
      <canvas ref={ref} width={WIDTH} height={HEIGHT} style={{ width: WIDTH, height: HEIGHT }} />
    </AbsoluteFill>
  );
};

/** The contact shadow + coloured ring spill on the floor under the hero object (from the reference's chip()). */
export const FloorShadow: React.FC<{ cx: number; cy: number; unit: number; ring?: number; white?: boolean; pitch?: number }> = ({
  cx,
  cy,
  unit,
  ring = 0,
  white = false,
  pitch = 0.36,
}) => {
  const sy = Math.max(0.18, Math.sin(pitch) * 0.8);
  const r = unit * 1.45;
  const r2 = unit * 1.9;
  const rr = Math.min(1.5, ring);
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: cx - r,
          top: cy - r * sy,
          width: r * 2,
          height: r * 2 * sy,
          borderRadius: "50%",
          background: `radial-gradient(closest-side, rgba(0,0,0,${white ? 0.32 : 0.75}), rgba(0,0,0,${white ? 0.1 : 0.3}) 60%, rgba(0,0,0,0))`,
        }}
      />
      {ring > 0.01 && !white ? (
        <div
          style={{
            position: "absolute",
            left: cx - r2,
            top: cy - r2 * sy,
            width: r2 * 2,
            height: r2 * 2 * sy,
            borderRadius: "50%",
            mixBlendMode: "screen",
            background: `radial-gradient(closest-side, rgba(170,110,255,${0.16 * rr}), rgba(255,130,90,${0.05 * rr}) 50%, rgba(0,0,0,0))`,
          }}
        />
      ) : null}
    </>
  );
};
