// The hero phone's continuous camera: pose keys (eased like the reference's keyed()), lighting, and the
// stage light that follows it. Scenes read poseAt(t) to anchor hairline callouts on the UI.
import { B, DURATION } from "./beats";
import { keyed, ringGlow, sm, map, clamp } from "./lib/h";
import { DEVICE_H, DEVICE_W, PhoneLight, PhonePose } from "./components/Phone";

type Key = { t: number; x: number; y: number; s: number; yaw: number; pitch: number; a: number };
const K = (t: number, x: number, y: number, s: number, yaw = 0, pitch = 0, a = 1): Key => ({ t, x, y, s, yaw, pitch, a });

const m = B.meet.cue,
  g = B.goal.cue,
  h = B.herd.cue,
  c = B.capture.cue,
  e = B.extract.cue,
  u = B.unclear.cue,
  p = B.passport.cue,
  pp = B.passportPage.cue,
  v = B.valuation.cue,
  ng = B.notGuaranteed.cue,
  gp = B.gap.cue,

  tr = B.tradeoffs.cue,
  pr = B.prepare.cue,
  ap = B.approve.cue,
  ac = B.activation.cue,
  cam = B.cameras.cue,
  nd = B.notDiagnosis.cue,
  ask = B.ask.cue,
  inc = B.incident.cue,
  ch = B.checklist.cue,
  su = B.submit.cue,
  au = B.audit.cue,
  bl = B.blocks.cue,
  cn = B.connects.cue,
  tg = B.tagline.cue;

export const KEYS: Key[] = [
  // reveal: rim light finds it centre-right, slow push + orbit
  K(0, 820, 372, 0.6, -0.42, 0.06, 0),
  K(m.meet - 0.3, 820, 372, 0.6, -0.42, 0.06, 0),
  K(m.meet + 0.3, 820, 372, 0.6, -0.42, 0.06, 1),
  K(m.onePlace + 0.4, 840, 366, 0.68, -0.16, 0.03),
  K(m.onePlace + 1.2, 840, 366, 0.68, -0.12, 0.03),
  // goal: orbits to the left of frame for the three promises
  K(g.know - 0.3, 360, 370, 0.66, 0.2, 0.02),
  K(B.goal.end, 380, 368, 0.7, 0.12, 0.02),
  // herd: centre-left over the barn
  K(h.herd + 0.2, 545, 384, 0.72, 0.1, 0),
  K(B.herd.end, 545, 384, 0.73, 0.06, 0),
  // enroll: the camera scan, pushed in
  K(c.add + 0.4, 820, 372, 0.76, -0.1, 0),
  K(c.body, 820, 372, 0.78, -0.06, 0),
  K(e.extracts, 820, 372, 0.74, -0.08, 0),
  K(e.confirm - 0.2, 860, 380, 0.8, -0.04, 0),
  K(B.extract.end + 0.15, 860, 380, 0.8, -0.04, 0),
  // unclear: slides left to share the stage with the "unclear" phone
  K(u.unclear - 0.1, 270, 390, 0.62, 0.12, 0),
  K(B.unclear.end, 270, 390, 0.62, 0.1, 0),
  // passport: centre, then right for the calculator
  K(p.confirmed + 0.2, 640, 376, 0.72, 0, 0),
  K(p.passport + 0.4, 640, 372, 0.74, -0.04, 0),
  K(pp.page + 0.2, 470, 372, 0.76, 0.1, 0),
  K(pp.docs + 0.6, 470, 372, 0.78, 0.08, 0),
  K(v.calculates + 0.3, 330, 372, 0.72, 0.16, 0),
  K(ng.payout + 0.4, 330, 372, 0.72, 0.12, 0),
  // insurance: agent conversation, pushed in close; cards lift out to the right
  K(gp.next + 0.1, 640, 380, 0.78, 0, 0),
  K(gp.assistant, 640, 380, 0.84, 0, 0),
  K(gp.three + 0.2, 250, 376, 0.72, 0.16, 0),
  K(B.plans.end, 250, 376, 0.72, 0.14, 0),
  K(tr.cheapest, 260, 376, 0.74, 0.12, 0),
  K(tr.choice + 0.4, 270, 376, 0.74, 0.1, 0),
  // approval: application, stamps, states rail
  K(pr.prepares, 400, 376, 0.78, 0.08, 0),
  K(ap.details, 380, 376, 0.8, 0.1, 0),
  K(ac.payment - 0.4, 300, 370, 0.7, 0.14, 0),
  K(B.cameras.start - 0.15, 300, 370, 0.7, 0.14, 1),
  // monitor: phone dissolves out for the CCTV full frame, comes back for Monitor
  K(B.cameras.start + 0.25, 300, 370, 0.7, 0.14, 0),
  K(cam.connects + 0.6, 180, 380, 0.62, 0.3, 0, 0),
  K(nd.inspect - 0.8, 180, 380, 0.62, 0.3, 0, 0),
  K(nd.inspect - 0.1, 860, 372, 0.74, -0.12, 0),
  K(B.notDiagnosis.end, 860, 372, 0.76, -0.1, 0),
  // ask
  K(ask.ask, 640, 376, 0.78, 0, 0),
  K(ask.answer + 0.3, 820, 372, 0.8, -0.08, 0),
  // claim: Bima
  K(inc.later, 400, 372, 0.76, 0.1, 0),
  K(ch.gathers, 420, 372, 0.78, 0.08, 0),
  K(B.missing.end + 0.2, 420, 372, 0.78, 0.08, 0),
  K(su.facts, 820, 372, 0.8, -0.08, 0),
  K(su.pending + 0.4, 820, 372, 0.8, -0.06, 0),
  // audit
  K(au.every, 400, 372, 0.78, 0.1, 0),
  K(bl.blocks + 0.4, 400, 372, 0.78, 0.08, 0),
  // close: hero beside the real cow, then the white stage
  K(cn.veyra, 860, 380, 0.72, -0.2, 0.03),
  K(tg.know - 0.2, 800, 455, 0.5, -0.12, 0.04),
  K(DURATION, 800, 456, 0.52, 0.05, 0.04),
];

export const poseAt = (t: number): PhonePose & { a: number } => keyed(KEYS, t);

// Lighting: rim first, key fades up, specular sweeps on reveals, edge ring ignites on "one place" and on
// the big confirmations (pulses).
const SWEEPS = [m.veyra + 0.3, p.passport, ac.confirms, cn.protection, tg.protect];
const PULSES = [m.onePlace, e.confirm, p.confirmed, ac.confirms, su.pending, tg.asset];

export function lightAt(t: number): PhoneLight & { stageKey: number; white: number } {
  let spec = -1;
  for (const s0 of SWEEPS) if (t > s0 - 0.1 && t < s0 + 1.6) spec = map(t, s0, s0 + 1.4, -0.25, 1.25);
  const ringBase = t < m.onePlace ? 0 : 0.25 * (1 - sm(B.goal.end, B.goal.end + 1, t)) + 0.6 * sm(m.onePlace, m.onePlace + 0.4, t) * (1 - sm(m.onePlace + 1.2, m.onePlace + 2.4, t));
  const white = sm(B.tagline.start - 0.35, B.tagline.start + 0.3, t); // the closing light-sweep wipe
  return {
    key: sm(m.meet + 0.4, m.meet + 1.8, t),
    rim: sm(m.meet - 0.1, m.meet + 0.9, t),
    spec,
    ring: clamp(ringGlow(ringBase, t, PULSES), 0, 1.6),
    ringRot: t * 0.3,
    white,
    stageKey: sm(m.meet + 0.4, m.meet + 1.8, t),
  };
}

/** a point on the screen (390x844 coordinates) -> stage pixels, for callout anchors */
export function toStage(pose: PhonePose, sx: number, sy: number): [number, number] {
  const lx = sx + 12 - DEVICE_W / 2,
    ly = sy + 12 - DEVICE_H / 2;
  return [pose.x + lx * pose.s * Math.cos(pose.yaw), pose.y + ly * pose.s];
}
export const phoneBottom = (pose: PhonePose) => pose.y + (DEVICE_H / 2) * pose.s;
export const phoneHalfW = (pose: PhonePose) => (DEVICE_W / 2) * pose.s;
