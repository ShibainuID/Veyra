import React from "react";
import { clamp, eo } from "../lib/h";

// The hero object: a graphite smartphone lit like the reference's slab. A machined metal band carries the
// softbox/horizon/floor-bounce banding, the rim light catches the edge that faces away from the key, a soft
// streak and a sweeping specular highlight glide over the glass, a conic violet->orange edge ring ignites on
// reveals, and the floor carries a fading reflection.
export const SCREEN_W = 390;
export const SCREEN_H = 844;
const BEZEL = 12;
export const DEVICE_W = SCREEN_W + BEZEL * 2;
export const DEVICE_H = SCREEN_H + BEZEL * 2;

export type PhonePose = { x: number; y: number; s: number; yaw: number; pitch: number; roll?: number };
export type PhoneLight = { key: number; rim: number; spec: number; ring: number; ringRot?: number; white?: number; reflect?: number };

const cc = (v: number, m: number) => `rgb(${Math.min(255, v * 0.96 * m) | 0},${Math.min(255, v * 0.98 * m) | 0},${Math.min(255, (v * 1.05 + 3) * m) | 0})`;

export const Phone: React.FC<{ pose: PhonePose; light: PhoneLight; children: React.ReactNode; opacity?: number }> = ({
  pose,
  light,
  children,
  opacity = 1,
}) => {
  const { key, rim, spec, ring } = light;
  const white = light.white ?? 0;
  // the reference's side-wall value: base + lambert*key + clamped spec/sheen*key + rim + white
  const v = 14 + 0.55 * 62 * key + 0.5 * 140 * key + rim * 50 + white * 40;
  const metal = `linear-gradient(180deg, ${cc(v, 1.32)} 0%, ${cc(v, 1.05)} 30%, ${cc(v, 0.62)} 52%, ${cc(v, 0.82)} 74%, ${cc(v, 0.42)} 100%)`;
  // rim catches the edge turned away from the key (the reference lights +X with the rim)
  const rimSide = pose.yaw >= 0 ? "left" : "right";
  const rimA = clamp(0.25 + 0.75 * rim) * (0.5 + 0.5 * Math.min(1, Math.abs(pose.yaw) * 3 + 0.4));
  const u = spec; // specular sweep position, visible in -0.3..1.3
  const showSpec = u > -0.3 && u < 1.3;
  const st = (o: number) => `${((u + o) * 100).toFixed(1)}%`;
  const reflect = (light.reflect ?? 1) * (white ? 0.22 : 0.45 * Math.max(0.2, key));
  return (
    <div
      style={{
        position: "absolute",
        left: pose.x,
        top: pose.y,
        width: 0,
        height: 0,
        perspective: 1700,
        opacity,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: -DEVICE_W / 2,
          top: -DEVICE_H / 2,
          width: DEVICE_W,
          height: DEVICE_H,
          transformOrigin: "50% 50%",
          transform: `scale(${pose.s}) rotateY(${pose.yaw}rad) rotateX(${pose.pitch}rad) rotateZ(${pose.roll ?? 0}rad)`,
          WebkitBoxReflect: reflect > 0.01 ? `below 22px linear-gradient(rgba(0,0,0,0) 64%, rgba(0,0,0,${reflect.toFixed(3)}))` : undefined,
        }}
      >
        {/* edge ring (behind the body so only its glow + outer line show) */}
        {ring > 0.01 ? (
          <div
            style={{
              position: "absolute",
              inset: -9,
              borderRadius: 74,
              padding: 2.6,
              background: `conic-gradient(from ${(light.ringRot ?? 0).toFixed(3)}rad, #b69cff, #e879f9, #ff9a4d, #5eead4, #6d7cff, #b69cff)`,
              WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
              WebkitMaskComposite: "xor",
              maskComposite: "exclude",
              opacity: Math.min(1, ring),
              filter: `drop-shadow(0 0 ${(16 * Math.min(1.6, ring)).toFixed(1)}px rgba(200,130,255,0.9))`,
            }}
          />
        ) : null}
        {/* machined metal band with a rim-lit chamfer edge */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 64,
            background: metal,
            boxShadow: [
              `inset 0 0 0 1px rgba(235,238,255,${(0.06 + 0.4 * key).toFixed(3)})`,
              `inset ${rimSide === "left" ? 2.5 : -2.5}px 0 0 rgba(235,238,255,${(0.95 * rimA).toFixed(3)})`,
              `${rimSide === "left" ? -1 : 1}px 0 18px rgba(200,210,255,${(0.18 * rim).toFixed(3)})`,
            ].join(", "),
          }}
        />
        {/* black glass bezel */}
        <div style={{ position: "absolute", inset: 4, borderRadius: 60, background: "#050507" }} />
        {/* screen */}
        <div
          style={{
            position: "absolute",
            left: BEZEL,
            top: BEZEL,
            width: SCREEN_W,
            height: SCREEN_H,
            borderRadius: 50,
            overflow: "hidden",
            background: "#fff",
          }}
        >
          {children}
          {/* dynamic island */}
          <div style={{ position: "absolute", left: SCREEN_W / 2 - 58, top: 11, width: 116, height: 34, borderRadius: 20, background: "#000" }} />
          {/* softbox reflection (glossy) */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `linear-gradient(180deg, rgba(255,255,255,${(0.16 * key).toFixed(3)}) 0%, rgba(255,255,255,${(0.035 * key).toFixed(3)}) 35%, rgba(255,255,255,0) 100%)`,
              mixBlendMode: "screen",
            }}
          />
          {/* fixed soft streak of the softbox on the glass */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `linear-gradient(120deg, rgba(255,255,255,0) 30%, rgba(255,255,255,${(0.11 * key).toFixed(3)}) 46%, rgba(255,255,255,${(0.05 * key).toFixed(3)}) 50%, rgba(255,255,255,0) 66%)`,
              mixBlendMode: "screen",
            }}
          />
          {/* specular sweep */}
          {showSpec ? (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: `linear-gradient(120deg, rgba(255,255,255,0) ${st(-0.16)}, rgba(255,255,255,0.08) ${st(-0.05)}, rgba(255,255,255,${(0.42 * key).toFixed(3)}) ${st(0)}, rgba(255,255,255,0.18) ${st(0.02)}, rgba(255,255,255,0) ${st(0.1)})`,
                mixBlendMode: "screen",
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
};

/** A finger tap on the screen (screen coordinates), drawn inside the phone screen. */
export const Tap: React.FC<{ t: number; at: number; x: number; y: number }> = ({ t, at, x, y }) => {
  const d = t - at;
  if (d < -0.25 || d > 0.7) return null;
  const pre = clamp((d + 0.25) / 0.25); // finger arriving
  const post = clamp(d / 0.6);
  const r = d < 0 ? 26 - 4 * pre : 22 + 40 * eo(post);
  const a = d < 0 ? 0.35 * pre : 0.35 * (1 - post);
  return (
    <div
      style={{
        position: "absolute",
        left: x - r,
        top: y - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        background: d < 0.05 ? `rgba(20,20,24,${a})` : "transparent",
        border: `3px solid rgba(20,20,24,${a})`,
        pointerEvents: "none",
      }}
    />
  );
};
