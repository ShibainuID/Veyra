import React from "react";
import { eo, mix, sm, io } from "../lib/h";
import { FILM, FONT } from "../theme";

// Typography from the reference: Inter, tight tracking (-3.5 % at >= 40 px), one-word-at-a-time reveal that
// focus-pulls from a 10 px blur, rises 28 % of the size and fades in over 0.6 s (ease-out cubic).

const track = (px: number) => (px >= 40 ? -Math.round(px * 0.035) : 0);

/** colour at fraction u along a gradient's stops */
function stopAt(stops: readonly string[], u: number) {
  const n = stops.length - 1;
  const k = Math.min(n - 1, Math.floor(u * n));
  const c = mix(stops[k], stops[k + 1], u * n - k);
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}

export type WordItem = { s: string; t: number; fill?: "grad" | string };

export const Words: React.FC<{
  list: readonly WordItem[];
  t: number;
  x: number;
  y: number; // alphabetic baseline
  px: number;
  weight?: number;
  align?: "left" | "center" | "right";
  fill?: string;
  stops?: readonly string[];
  dur?: number;
  blur?: number;
  alpha?: number;
  glow?: boolean;
  style?: React.CSSProperties;
}> = ({ list, t, x, y, px, weight = 800, align = "left", fill = FILM.INK, stops = FILM.GV, dur = 0.6, blur = 10, alpha = 1, glow, style }) => {
  const gradIdx = list.map((w, i) => (w.fill === "grad" ? i : -1)).filter((i) => i >= 0);
  const g0 = gradIdx[0] ?? 0;
  const gn = Math.max(1, gradIdx.length);
  const tx = align === "center" ? "-50%" : align === "right" ? "-100%" : "0";
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y - px * 0.93,
        translate: `${tx} 0`,
        whiteSpace: "nowrap",
        fontFamily: FONT.film,
        fontWeight: weight,
        fontSize: px,
        lineHeight: 1.15,
        letterSpacing: track(px),
        ...style,
      }}
    >
      {list.map((it, i) => {
        const e = eo((t - it.t) / dur);
        const b = (1 - e) * blur;
        let color: React.CSSProperties = { color: it.fill && it.fill !== "grad" ? it.fill : fill };
        if (it.fill === "grad") {
          const k = i - g0;
          color = {
            backgroundImage: `linear-gradient(90deg, ${stopAt(stops, k / gn)}, ${stopAt(stops, (k + 1) / gn)})`,
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
            filter: [b > 0.3 ? `blur(${b.toFixed(1)}px)` : "", glow ? "drop-shadow(0 0 18px rgba(220,110,255,0.45))" : ""].join(" ") || undefined,
          };
        }
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              marginRight: i < list.length - 1 ? px * 0.27 + px * 0.08 : 0,
              opacity: e * alpha,
              translate: `0 ${(1 - e) * px * 0.28}px`,
              filter: it.fill !== "grad" && b > 0.3 ? `blur(${b.toFixed(1)}px)` : undefined,
              ...color,
            }}
          >
            {it.s}
          </span>
        );
      })}
    </div>
  );
};

/** split "Know every animal." into word items starting at t0 spaced by gap (or given times) */
export const seq = (text: string, times: number | readonly number[], gap = 0.22, fill?: WordItem["fill"]): WordItem[] =>
  text.split(" ").map((s, i) => ({ s, t: Array.isArray(times) ? (times as number[])[Math.min(i, times.length - 1)] : (times as number) + i * gap, fill }));

export const Label: React.FC<{
  x: number;
  y: number;
  px?: number;
  weight?: number;
  color?: string;
  align?: "left" | "center" | "right";
  opacity?: number;
  mono?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ x, y, px = 28, weight = 600, color = FILM.INK, align = "left", opacity = 1, mono, children, style }) => {
  const tx = align === "center" ? "-50%" : align === "right" ? "-100%" : "0";
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y - px * 0.93,
        translate: `${tx} 0`,
        whiteSpace: "nowrap",
        fontFamily: mono ? FONT.mono : FONT.film,
        fontVariantNumeric: "tabular-nums slashed-zero",
        fontWeight: weight,
        fontSize: px,
        lineHeight: 1.15,
        letterSpacing: track(px),
        color,
        opacity,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Big gradient key number with the reference's glow bloom and an optional gleam pass (0..1). */
export const GradNumber: React.FC<{
  x: number;
  y: number;
  px: number;
  text: string;
  opacity?: number;
  stops?: readonly string[];
  glow?: number; // 0..1 extra bloom (the "lock")
  gleam?: number; // -1 = none, 0..1 sweep position
  align?: "left" | "center" | "right";
  scale?: number;
}> = ({ x, y, px, text, opacity = 1, stops = FILM.GV, glow = 0, gleam = -1, align = "left", scale = 1 }) => {
  const tx = align === "center" ? "-50%" : align === "right" ? "-100%" : "0";
  const base: React.CSSProperties = {
    position: "absolute",
    left: 0,
    top: 0,
    whiteSpace: "nowrap",
    fontFamily: FONT.film,
    fontWeight: 800,
    fontSize: px,
    lineHeight: 1.15,
    letterSpacing: track(px),
    fontVariantNumeric: "tabular-nums",
  };
  return (
    <div style={{ position: "absolute", left: x, top: y - px * 0.93, translate: `${tx} 0`, opacity, scale, transformOrigin: "left center" }}>
      <div style={{ ...base, position: "relative" }}>
        <span
          style={{
            backgroundImage: `linear-gradient(90deg, ${stops.join(", ")})`,
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
            filter: `drop-shadow(0 0 ${(25 + 30 * glow).toFixed(0)}px rgba(220,110,255,${(0.45 + 0.35 * glow).toFixed(2)}))`,
          }}
        >
          {text}
        </span>
        {gleam > 0 && gleam < 1 ? (
          <span
            style={{
              ...base,
              backgroundImage: `linear-gradient(90deg, rgba(255,255,255,0) ${gleam * 140 - 30}%, rgba(255,255,255,0.85) ${gleam * 140 - 20}%, rgba(255,255,255,0) ${gleam * 140 - 10}%)`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            {text}
          </span>
        ) : null}
      </div>
    </div>
  );
};

/** The reference's clean red strike, drawn left to right over [x0, x1] at height y with progress p. */
export const Strike: React.FC<{ x0: number; x1: number; y: number; p: number; width?: number }> = ({ x0, x1, y, p, width = 4 }) =>
  p <= 0 ? null : (
    <div
      style={{
        position: "absolute",
        left: x0,
        top: y - width / 2,
        width: (x1 - x0) * io(p),
        height: width,
        borderRadius: width,
        background: FILM.RED,
        boxShadow: "0 0 12px rgba(255,69,58,0.55)",
      }}
    />
  );

// ---------- hairline callout: anchor dot -> elbow -> end, label sits at the end ----------
export type Pt = readonly [number, number];
export const Callout: React.FC<{
  pts: readonly Pt[];
  p: number;
  label: string;
  sub?: string;
  side: "l" | "r";
  ink?: string; // "255,255,255"
  px?: number;
  subPx?: number;
  labFill?: string;
  subFill?: string;
}> = ({ pts, p, label, sub, side, ink = "255,255,255", px = 30, subPx = 28, labFill, subFill = FILM.GREY }) => {
  if (p <= 0) return null;
  const A = pts[0];
  const e = eo(p / 0.35);
  let len = 0;
  for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  const drawn = len * io(sm(0.1, 0.75, p));
  const d = "M" + pts.map((q) => `${q[0]},${q[1]}`).join(" L");
  const la = sm(0.6, 1, p);
  const E = pts[pts.length - 1];
  const dx = (1 - la) * 10 * (side === "r" ? 1 : -1);
  const tx = side === "r" ? E[0] + 14 + dx : E[0] - 14 + dx;
  return (
    <>
      <svg width={1280} height={720} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
        <circle cx={A[0]} cy={A[1]} r={3.6} fill={`rgba(${ink},${0.95 * e})`} />
        <circle cx={A[0]} cy={A[1]} r={5 + 6 * e} fill="none" stroke={`rgba(${ink},${0.35 * e})`} strokeWidth={1} />
        <path d={d} fill="none" stroke={`rgba(${ink},0.7)`} strokeWidth={1} strokeDasharray={`${drawn} ${len + 10}`} />
      </svg>
      {la > 0 ? (
        <>
          <Label x={tx} y={E[1] + 10} px={px} weight={600} color={labFill ?? `rgb(${ink})`} align={side === "r" ? "left" : "right"} opacity={la}>
            {label}
          </Label>
          {sub ? (
            <Label x={tx} y={E[1] + 10 + px * 1.12} px={subPx} weight={400} color={subFill} align={side === "r" ? "left" : "right"} opacity={la}>
              {sub}
            </Label>
          ) : null}
        </>
      ) : null}
    </>
  );
};

/** callout progress for a cue: the reference's sm(t0, t0 + 0.9, t) */
export const cp = (t: number, t0: number, dur = 0.9) => sm(t0, t0 + dur, t);
