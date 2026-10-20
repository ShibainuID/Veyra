import React, { createContext, useContext, useEffect, useState } from "react";
import { Video } from "@remotion/media";
import { continueRender, delayRender, getStaticFiles, Img, Sequence, staticFile, useVideoConfig } from "remotion";
import { useOffsetFrames } from "../lib/time";

// Real phone-viewport captures of the app (390x844 @2x) live in public/app/ with a captures.json manifest.
// <PhoneScreen capture="herd" moment="..."> plays the capture from that moment when it exists, and otherwise
// renders its children: a faithful recreation of that screen state in the Ear Tag style.

export type CaptureEntry = { video?: string; still?: string; moments: Record<string, number> };
type Captures = Record<string, CaptureEntry>;

const Ctx = createContext<Captures>({});
const MANIFEST = "app/captures.json";

// Accepts { name: {mp4|video, png|still, moments: {k: s} | [{name|label, t|time|s}]} } or { files|captures: [...] }.
function normalize(json: unknown): Captures {
  const out: Captures = {};
  const add = (name: string, e: Record<string, unknown>) => {
    const file = (k: string[]) => {
      for (const key of k) if (typeof e[key] === "string") return (e[key] as string).replace(/^\.?\/?(public\/)?(app\/)?/, "");
      return undefined;
    };
    const moments: Record<string, number> = {};
    const m = e.moments ?? e.keyMoments ?? e.key_moments ?? e.timestamps;
    if (Array.isArray(m)) {
      for (const it of m as Record<string, unknown>[]) {
        const k = (it.name ?? it.label ?? it.id ?? it.moment) as string | undefined;
        const v = (it.t ?? it.time ?? it.s ?? it.seconds ?? it.at) as number | undefined;
        if (k && typeof v === "number") moments[k] = v;
      }
    } else if (m && typeof m === "object") {
      for (const [k, v] of Object.entries(m as Record<string, unknown>)) {
        if (typeof v === "number") moments[k] = v;
        else if (v && typeof v === "object" && typeof (v as { t?: number }).t === "number") moments[k] = (v as { t: number }).t;
      }
    }
    out[name] = { video: file(["mp4", "video", "file", "src"]), still: file(["png", "still", "image", "poster"]), moments };
  };
  if (Array.isArray(json)) json.forEach((e) => add(String(e.name ?? e.id), e));
  else if (json && typeof json === "object") {
    const j = json as Record<string, unknown>;
    const list = j.files ?? j.captures ?? j.flows;
    if (Array.isArray(list)) list.forEach((e: Record<string, unknown>) => add(String(e.name ?? e.id ?? e.flow), e));
    else if (list && typeof list === "object") Object.entries(list).forEach(([k, e]) => add(k, e as Record<string, unknown>));
    else Object.entries(j).forEach(([k, e]) => e && typeof e === "object" && add(k, e as Record<string, unknown>));
  }
  return out;
}

export const CapturesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const has = getStaticFiles().some((f) => f.name === MANIFEST);
  const [data, setData] = useState<Captures>({});
  const [handle] = useState(() => (has ? delayRender("Loading app captures manifest") : null));
  useEffect(() => {
    if (handle === null) return;
    fetch(staticFile(MANIFEST))
      .then((r) => r.json())
      .then((j) => setData(normalize(j)))
      .catch(() => setData({}))
      .finally(() => continueRender(handle));
  }, [handle]);
  return <Ctx.Provider value={data}>{children}</Ctx.Provider>;
};

const exists = (file?: string) => !!file && getStaticFiles().some((f) => f.name === `app/${file}`);

export function useCapture(name?: string): CaptureEntry | null {
  const all = useContext(Ctx);
  if (!name) return null;
  const e = all[name];
  if (!e) return null;
  return exists(e.video) || exists(e.still) ? e : null;
}

/**
 * capture: manifest name ("herd", "passport", ...). moment: a key moment in that capture.
 * since: absolute film time when this screen state starts (the capture plays from the moment at that time).
 */
export const PhoneScreen: React.FC<{
  capture?: string;
  moment?: string;
  since?: number;
  until?: number;
  children: React.ReactNode;
}> = ({ capture, moment, since = 0, until, children }) => {
  const cap = useCapture(capture);
  const { fps } = useVideoConfig();
  const off = useOffsetFrames();
  if (!cap) return <>{children}</>;
  const m = moment && cap.moments[moment] != null ? cap.moments[moment] : 0;
  const style: React.CSSProperties = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" };
  if (cap.video && exists(cap.video)) {
    const from = Math.round(since * fps);
    return (
      <Sequence from={from - off} durationInFrames={until ? Math.max(1, Math.round(until * fps) - from) : undefined} premountFor={fps}>
        <Video src={staticFile(`app/${cap.video}`)} trimBefore={Math.round(m * fps)} muted objectFit="cover" style={style} />
      </Sequence>
    );
  }
  return <Img src={staticFile(`app/${cap.still}`)} style={style} />;
};
