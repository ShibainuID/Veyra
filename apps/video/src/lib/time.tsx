import React, { createContext, useContext } from "react";
import { Sequence, useCurrentFrame, useVideoConfig } from "remotion";

// Scenes are Remotion <Sequence>s (so they show up and premount in the Studio timeline), but every animation
// reads ABSOLUTE film time from BEATS. useT() adds the scene's offset back.
const Offset = createContext(0);

/** frames to subtract from an absolute frame to place a child <Sequence> inside the current scene */
export const useOffsetFrames = () => useContext(Offset);

export function useT() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const off = useContext(Offset);
  return (frame + off) / fps;
}

export const Scene: React.FC<{ name: string; start: number; end: number; children: React.ReactNode }> = ({
  name,
  start,
  end,
  children,
}) => {
  const { fps } = useVideoConfig();
  const from = Math.round(start * fps);
  return (
    <Sequence name={name} from={from} durationInFrames={Math.max(1, Math.round(end * fps) - from)} premountFor={fps}>
      <Offset.Provider value={from}>{children}</Offset.Provider>
    </Sequence>
  );
};

/** Visible between a and b (with optional fades), as 0..1 */
export function win(t: number, a: number, b: number, fadeIn = 0.4, fadeOut = 0.4) {
  if (t < a || t > b) return 0;
  const i = fadeIn > 0 ? Math.min(1, (t - a) / fadeIn) : 1;
  const o = fadeOut > 0 ? Math.min(1, (b - t) / fadeOut) : 1;
  return Math.max(0, Math.min(i, o));
}
