/**
 * The muzzle guide box drawn on the capture screen. The ML crop (services/api/adapters/perception.py
 * `guide_box_crop`, workers/video_enrollment.py `muzzle_crop`) cuts exactly this box out of each frame, so
 * the overlay must use the same arithmetic, integer truncation included:
 *
 *   cw = int(0.9 * w); ch = min(h, int(cw / 1.18)); cw = min(cw, int(ch * 1.18)); centred.
 *
 * On a landscape frame the height limits the box; on a portrait (phone) frame it is the full 90% width.
 */

export const MUZZLE_GUIDE_WIDTH = 0.9;
export const MUZZLE_GUIDE_ASPECT = 1.18;

export interface GuideBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function muzzleGuideBox(frameWidth: number, frameHeight: number): GuideBox {
  const w = Math.max(0, Math.trunc(frameWidth));
  const h = Math.max(0, Math.trunc(frameHeight));
  let cw = Math.trunc(MUZZLE_GUIDE_WIDTH * w);
  const ch = Math.min(h, Math.trunc(cw / MUZZLE_GUIDE_ASPECT));
  cw = Math.min(cw, Math.trunc(ch * MUZZLE_GUIDE_ASPECT));
  return { x: Math.floor((w - cw) / 2), y: Math.floor((h - ch) / 2), width: cw, height: ch };
}

/** The guided prompts, in capture order. One continuous recording walks through all three. */
export const CAPTURE_PROMPTS = [
  { view: "muzzle", title: "Muzzle: fill the box", detail: "Hold steady, nose centred, the muzzle filling the yellow box.", seconds: 6 },
  { view: "teeth", title: "Teeth: open mouth view", detail: "Lift the lip so the front incisors show.", seconds: 6 },
  {
    view: "body",
    title: "Body: full side view with the ArUco marker on the flank",
    detail: "Step back until the whole side is in frame, the printed marker flat on the flank.",
    seconds: 8,
  },
] as const;

export type CaptureView = (typeof CAPTURE_PROMPTS)[number]["view"];

/** Which prompt applies after `elapsedS` seconds of recording, if the operator has not tapped ahead. */
export function promptIndexAt(elapsedS: number): number {
  let end = 0;
  for (let i = 0; i < CAPTURE_PROMPTS.length; i++) {
    end += CAPTURE_PROMPTS[i]!.seconds;
    if (elapsedS < end) return i;
  }
  return CAPTURE_PROMPTS.length - 1;
}
