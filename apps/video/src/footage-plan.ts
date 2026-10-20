// Shared live-action timing, so the phone's camera preview and the real scene behind it stay frame-locked.
import { B } from "./beats";
import { Segment } from "./components/Footage";

const c = B.capture.cue;
const e = B.extract.cue;

// The guided phone recording (video_hp.mp4): 0-3.4 s muzzle close-up, 3.4-5 s pulling back, 5-8 s body side-on.
export const SCAN_SEGMENTS: Segment[] = [
  { clip: "hp", start: B.capture.start - 0.4, end: c.teeth, from: 0.0, rate: 0.5 }, // muzzle, slowed (steady hold)
  { clip: "hp", start: c.teeth, end: c.body, from: (c.teeth - (B.capture.start - 0.4)) * 0.5, rate: 1.0 }, // mouth / lower lip
  { clip: "hp", start: c.body, end: e.extracts + 0.2, from: 3.7, rate: 2.0 }, // step back to the full body
];

// The "unclear" take: the moving, soft-focus moment of the same recording (around 3.3-3.6 s), slowed right down.
export const UNCLEAR_SEGMENTS: Segment[] = [{ clip: "hp", start: B.unclear.start - 0.6, end: B.passport.start + 0.6, from: 3.25, rate: 0.12 }];

// Barn CCTV (video_cctv.mp4) for the monitoring beats: one slow forward pass (no reversed motion on a real camera).
export const CCTV_START = B.cameras.start - 0.1;
export const CCTV_END = B.notDiagnosis.cue.inspect + 0.4;
export const CCTV_SEGMENTS: Segment[] = [{ clip: "cctv", start: CCTV_START, end: CCTV_END, from: 0.0, rate: 7.9 / (CCTV_END - CCTV_START) }];
// the same camera, replayed inside the phone's Monitor screen (the associated cow in the scan zone)
export const MONITOR_PHONE_SEGMENTS: Segment[] = [{ clip: "cctv", start: B.notDiagnosis.cue.inspect - 0.9, end: B.ask.start + 0.6, from: 1.0, rate: 0.6 }];
