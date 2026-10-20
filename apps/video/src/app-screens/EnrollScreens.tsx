import React from "react";
import { Camera, CircleCheck, RotateCcw, ScanLine, UploadCloud } from "lucide-react";
import { APP } from "../theme";
import { Footage, Segment, Still } from "../components/Footage";
import { clamp, sm } from "../lib/h";
import { OPERATOR, SARI } from "./data";
import { Btn, EarTag, EvidenceFrame, Pill, Prov, Rule, Shell, Stamp, T, mono, rise } from "./ui";
import { Tap } from "../components/Phone";

// Guide box: the app's arithmetic (guide-box.ts): 90 % of the portrait frame width, aspect 1.18.
const CAM_TOP = 106,
  CAM_H = 844 - 106 - 82;
export const GUIDE = (() => {
  const w = Math.trunc(0.9 * 390);
  const h = Math.min(CAM_H, Math.trunc(w / 1.18));
  return { x: Math.floor((390 - w) / 2), y: CAM_TOP + Math.floor((CAM_H - h) / 2), w, h };
})();

export const PROMPTS = {
  muzzle: { title: "Muzzle: fill the box", detail: "Hold steady, nose centred" },
  teeth: { title: "Teeth: open mouth view", detail: "Lift the lip so the incisors show" },
  body: { title: "Body: full side view", detail: "Step back until the whole side is in frame" },
};

/** Scan Cow: the phone's own camera, guided. */
export const ScanScreen: React.FC<{
  t: number;
  segments: Segment[];
  recAt: number;
  teethAt: number;
  bodyAt: number;
  qualityFrom: number;
  qualityTo: number;
  capturedAt: number;
}> = ({ t, segments, recAt, teethAt, bodyAt, qualityFrom, qualityTo, capturedAt }) => {
  const step = t >= bodyAt ? "body" : t >= teethAt ? "teeth" : "muzzle";
  const pr = PROMPTS[step];
  const q = clamp((t - qualityFrom) / (qualityTo - qualityFrom));
  const secs = Math.max(0, t - recAt);
  const flash = t > capturedAt && t < capturedAt + 0.35 ? 1 - (t - capturedAt) / 0.35 : 0;
  const boxOn = step === "muzzle" ? 1 : 1 - sm(teethAt, teethAt + 0.4, t);
  return (
    <Shell time="09:12" tab="enroll" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Enroll · Scan cow</span>}>
      <div style={{ position: "relative", height: CAM_H, background: "#000", overflow: "hidden" }}>
        <Footage name="Phone camera" segments={segments} frame={{ zoom: step === "body" ? 1 : 1.05, fx: 0.42, fy: 0.5, dx: 70 }} filter="contrast(1.04) saturate(1.02)" />
        {/* guide box */}
        <div
          style={{
            position: "absolute",
            left: GUIDE.x,
            top: GUIDE.y - CAM_TOP,
            width: GUIDE.w,
            height: GUIDE.h,
            border: `3px solid ${q >= 1 && step === "muzzle" ? APP.ok : APP.tag}`,
            borderRadius: 12,
            boxShadow: "0 0 0 2000px rgba(0,0,0,0.28)",
            opacity: boxOn,
            boxSizing: "border-box",
          }}
        />
        {/* prompt */}
        <div style={{ position: "absolute", left: 12, right: 12, top: 12, display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div style={{ background: "rgba(20,20,22,0.9)", borderRadius: 10, padding: "8px 12px", color: "#fff" }}>
            <div style={{ ...mono, fontSize: 13.5, color: APP.onShellMuted }}>Step {step === "muzzle" ? 1 : step === "teeth" ? 2 : 3} of 3</div>
            <div style={{ fontWeight: 700, fontSize: 17, color: APP.tag }}>{pr.title}</div>
            <div style={{ fontSize: 14, color: APP.onShellMuted }}>{pr.detail}</div>
          </div>
          <div style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 6, background: "rgba(20,20,22,0.9)", borderRadius: 10, padding: "8px 10px", color: "#fff", ...mono, fontWeight: 700, fontSize: 15 }}>
            <span style={{ width: 11, height: 11, borderRadius: 6, background: APP.danger }} />
            {`00:${String(Math.floor(secs)).padStart(2, "0")}`}
          </div>
        </div>
        {/* quality meter */}
        <div style={{ position: "absolute", left: 12, right: 12, bottom: 12, background: "rgba(20,20,22,0.9)", borderRadius: 10, padding: "10px 12px", color: "#fff" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, fontSize: 15 }}>
            <span>Muzzle quality</span>
            <span style={{ color: q >= 1 ? "#7be0a6" : APP.tag }}>{q >= 1 ? "Good · frame captured" : q > 0.5 ? "Possible match" : "Checking…"}</span>
          </div>
          <div style={{ height: 8, borderRadius: 4, background: "rgba(255,255,255,0.18)", marginTop: 8, overflow: "hidden" }}>
            <div style={{ width: `${q * 100}%`, height: "100%", background: q >= 1 ? "#5fd394" : APP.tag }} />
          </div>
        </div>
        <div style={{ position: "absolute", inset: 0, background: `rgba(255,255,255,${0.7 * flash})` }} />
      </div>
    </Shell>
  );
};

const FRAMES = [
  { view: "Muzzle", at: "0:01.5", src: "footage/hp_muzzle.jpg", frame: { zoom: 1.5, fx: 0.38, fy: 0.42 } },
  { view: "Teeth", at: "0:03.2", src: "footage/hp_muzzle.jpg", frame: { zoom: 2.4, fx: 0.38, fy: 0.95 } },
  { view: "Body", at: "0:06.0", src: "footage/hp_body_side.jpg", frame: { zoom: 1.2, fx: 0.45, fy: 0.5 } },
];
export const EXTRACT_FRAMES = FRAMES;

/** Upload -> extracted reference frames -> identity candidate -> Confirm identity (a person taps it). */
export const ReviewScreen: React.FC<{ t: number; uploadAt: number; framesAt: number; candidateAt: number; confirmAt: number }> = ({
  t,
  uploadAt,
  framesAt,
  candidateAt,
  confirmAt,
}) => {
  const up = clamp((t - uploadAt) / (framesAt - uploadAt - 0.1));
  const confirmed = t >= confirmAt;
  return (
    <Shell time="09:14" tab="enroll" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Enroll · Review</span>}>
      <div style={{ padding: "16px 16px 0" }}>
        {t < framesAt ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700, fontSize: T.title }}>
              <UploadCloud size={26} strokeWidth={2.25} /> Uploading guided video
            </div>
            <div style={{ ...mono, color: APP.muted, fontSize: 15 }}>sari-guided.mp4 · 00:08 · one take</div>
            <div style={{ height: 10, borderRadius: 5, background: APP.surface2, overflow: "hidden" }}>
              <div style={{ width: `${up * 100}%`, height: "100%", background: APP.ink }} />
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 700, fontSize: T.title }}>Reference frames</span>
              <Prov kind="prototype" />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              {FRAMES.map((f, i) => (
                <div key={f.view} style={{ ...rise(t, framesAt + i * 0.18), flex: 1 }}>
                  <EvidenceFrame w={114} h={96}>
                    <Still src={f.src} frame={f.frame} />
                  </EvidenceFrame>
                  <div style={{ fontWeight: 700, fontSize: 15, marginTop: 6 }}>{f.view}</div>
                  <div style={{ ...mono, fontSize: 13.5, color: APP.muted }}>{f.at}</div>
                </div>
              ))}
            </div>
            <Rule w={2} color={APP.ink} style={{ margin: "16px 0" }} />
            <div style={{ ...rise(t, candidateAt) }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <EarTag num={SARI.tag} state={confirmed ? "confirmed" : "pending"} h={56} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: 21 }}>{SARI.name}</div>
                  <div style={{ ...mono, fontSize: 14.5, color: APP.muted }}>{SARI.id}</div>
                </div>
              </div>
              <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Pill tone="neutral" label="New animal · no verified match" />
              </div>
              <div style={{ marginTop: 6, fontSize: 15.5, color: APP.muted }}>Closest on file: Rama (006), 3 points. Not a match.</div>
              <div style={{ marginTop: 14 }}>
                {confirmed ? (
                  <Stamp kind="confirmed" text={`Confirmed · 20 Oct 09:14 · ${OPERATOR.initials}`} press={t - confirmAt} size={1.1} />
                ) : (
                  <Btn label="Confirm identity" icon={CircleCheck} full pressed={t > confirmAt - 0.12} />
                )}
              </div>
            </div>
          </>
        )}
      </div>
      <Tap t={t} at={confirmAt} x={195} y={590} />
    </Shell>
  );
};

/** The 'Unclear - review required' variant: the record stays unconfirmed instead of guessing. */
export const UnclearScreen: React.FC<{ t: number; segments: Segment[]; t0: number }> = ({ t, segments, t0 }) => (
  <Shell time="09:20" tab="enroll" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Enroll · Review</span>}>
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontWeight: 700, fontSize: T.title }}>Muzzle view</span>
        <Prov kind="prototype" />
      </div>
      <div style={{ marginTop: 12 }}>
        <EvidenceFrame w={358} h={250}>
          <Footage name="Unclear take" segments={segments} frame={{ zoom: 1.25, fx: 0.42, fy: 0.45 }} filter="blur(5px) brightness(0.95)" />
        </EvidenceFrame>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, ...rise(t, t0 + 0.3) }}>
        <EarTag state="pending" num="---" h={56} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 21 }}>Unconfirmed</div>
          <div style={{ ...mono, fontSize: 14.5, color: APP.muted }}>no animal ID assigned</div>
        </div>
      </div>
      <div style={{ marginTop: 12, ...rise(t, t0 + 0.5) }}>
        <Pill tone="uncertain" label="Unclear — review required" />
      </div>
      <div style={{ marginTop: 8, fontSize: 15.5, color: APP.muted, ...rise(t, t0 + 0.6) }}>Muzzle too blurred to match. Nothing is linked until a person reviews it.</div>
      <div style={{ display: "flex", gap: 10, marginTop: 14, ...rise(t, t0 + 0.7) }}>
        <Btn v="secondary" label="Retake muzzle" icon={RotateCcw} />
        <Stamp kind="awaiting" text="Awaiting review" />
      </div>
    </div>
  </Shell>
);

export const EnrollStart: React.FC = () => (
  <Shell time="09:11" tab="enroll" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Enroll</span>}>
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <span style={{ fontWeight: 700, fontSize: T.h1 }}>Enroll a cow</span>
      <span style={{ fontSize: T.body, color: APP.muted }}>Record one continuous video: muzzle, then teeth, then the full body.</span>
      <Btn label="Start guided video" icon={Camera} full />
      <Btn v="secondary" label="Upload a video" icon={ScanLine} full />
    </div>
  </Shell>
);
