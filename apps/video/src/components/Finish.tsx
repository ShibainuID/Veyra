import React, { useMemo } from "react";
import { AbsoluteFill } from "remotion";
import { rng } from "../lib/h";

// The reference's finish(): a 0.55 vignette on the dark stage, then a 256 px seeded film-grain tile composited with
// soft-light at 6 % (4 % on the white stage), re-offset 24 times a second. Same strength, every frame.
let GRAIN: string | null = null;
function grainTile() {
  if (GRAIN) return GRAIN;
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const img = g.createImageData(256, 256);
  const r = rng(77);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = r() * 255;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  GRAIN = c.toDataURL("image/png");
  return GRAIN;
}

export const Finish: React.FC<{ t: number; white?: number }> = ({ t, white = 0 }) => {
  const tile = useMemo(() => grainTile(), []);
  const r = rng(900 + Math.floor(t * 24));
  const ox = -Math.floor(r() * 256);
  const oy = -Math.floor(r() * 256);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* H.vignette(ctx, W, H, 0.55): radial from min(W,H)*0.3 = 216 px to hypot(W,H)*0.6 = 881 px */}
      <AbsoluteFill
        style={{
          opacity: 1 - white,
          background: "radial-gradient(circle at 50% 50%, rgba(0,0,0,0) 216px, rgba(0,0,0,0.55) 881px)",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.06 - 0.02 * white,
          mixBlendMode: "soft-light",
          // a data: URL generated synchronously, so it is always loaded before the frame is captured
          // eslint-disable-next-line @remotion/no-background-image
          backgroundImage: `url(${tile})`,
          backgroundRepeat: "repeat",
          backgroundPosition: `${ox}px ${oy}px`,
        }}
      />
    </AbsoluteFill>
  );
};
