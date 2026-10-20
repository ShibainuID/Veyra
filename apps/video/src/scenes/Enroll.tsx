import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Footage, Still } from "../components/Footage";
import { Phone } from "../components/Phone";
import { FloorShadow } from "../components/Stage";
import { Label, Words } from "../components/Type";
import { EXTRACT_FRAMES, UnclearScreen } from "../app-screens/EnrollScreens";
import { SCAN_SEGMENTS, UNCLEAR_SEGMENTS } from "../footage-plan";
import { eo, io, lerp, sm } from "../lib/h";
import { useT } from "../lib/time";
import { lightAt } from "../phone-track";
import { FILM, FONT } from "../theme";

// 00:46-01:03 Enrollment with the phone's own camera: muzzle -> teeth -> body, frames extracted, a person
// confirms; an unclear take stays unconfirmed.
const c = B.capture.cue;
const e = B.extract.cue;
const u = B.unclear.cue;

export const EnrollBack: React.FC = () => {
  const t = useT();
  const a = sm(B.capture.start - 0.4, B.capture.start + 0.3, t) * (1 - sm(e.extracts - 0.1, e.extracts + 0.6, t));
  return (
    <AbsoluteFill style={{ opacity: a }}>
      {/* the real scene, frame-locked to the phone's preview */}
      <Footage name="Cow (real scene)" segments={SCAN_SEGMENTS} frame={{ zoom: 1.08, fx: 0.4, fy: 0.5 }} filter="blur(3px) brightness(0.5) saturate(0.9)" />
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(3,3,4,0.82) 0%, rgba(3,3,4,0.55) 45%, rgba(3,3,4,0.15) 70%, rgba(3,3,4,0.35) 100%)" }} />
    </AbsoluteFill>
  );
};

const Step: React.FC<{ y: number; label: string; t: number; at: number; done: number }> = ({ y, label, t, at, done }) => {
  const a = eo((t - at) / 0.4);
  const d = eo((t - done) / 0.3);
  return (
    <div style={{ position: "absolute", left: 96, top: y - 30, display: "flex", alignItems: "center", gap: 18, opacity: 0.35 + 0.65 * a }}>
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: 17,
          border: `2px solid ${a > 0.5 ? FILM.MINT : "rgba(255,255,255,0.5)"}`,
          background: d > 0 ? `rgba(124,240,184,${d})` : "transparent",
          display: "grid",
          placeItems: "center",
          color: "#062",
          fontWeight: 800,
          fontSize: 20,
          fontFamily: FONT.film,
        }}
      >
        {d > 0.5 ? "✓" : ""}
      </div>
      <span style={{ fontFamily: FONT.film, fontWeight: 600, fontSize: 40, color: FILM.INK, letterSpacing: -1 }}>{label}</span>
    </div>
  );
};

export const EnrollFront: React.FC = () => {
  const t = useT();
  const capA = sm(B.capture.start - 0.2, B.capture.start + 0.4, t) * (1 - sm(e.extracts - 0.2, e.extracts + 0.3, t));
  const exA = sm(e.extracts - 0.1, e.extracts + 0.3, t) * (1 - sm(u.unclear - 0.5, u.unclear, t));
  const unA = sm(u.unclear - 0.3, u.unclear + 0.3, t) * (1 - sm(B.passport.start - 0.2, B.passport.start + 0.4, t));
  // the second phone enters from the right
  const enter = io(sm(u.unclear - 0.4, u.unclear + 0.5, t));
  const leave = io(sm(B.passport.start - 0.3, B.passport.start + 0.5, t));
  const light = lightAt(t);
  const pose2 = { x: lerp(1500, 620, enter) + 900 * leave, y: 390, s: 0.62, yaw: -0.12, pitch: 0 };
  return (
    <AbsoluteFill>
      {capA > 0 ? (
        <AbsoluteFill style={{ opacity: capA }}>
          <Words list={[{ s: "One", t: c.guided - 0.35 }, { s: "guided", t: c.guided, fill: "grad" }, { s: "video.", t: c.guided + 0.38, fill: "grad" }]} t={t} x={96} y={190} px={60} />
          <Label x={98} y={244} px={28} weight={400} color={FILM.GREY} opacity={sm(c.uploads, c.uploads + 0.4, t)}>
            Recorded with the phone camera
          </Label>
          <Step y={340} label="Muzzle" t={t} at={c.nose} done={c.teeth - 0.2} />
          <Step y={420} label="Teeth" t={t} at={c.teeth} done={c.body - 0.1} />
          <Step y={500} label="Full body" t={t} at={c.body} done={e.extracts - 0.1} />
        </AbsoluteFill>
      ) : null}
      {exA > 0 ? (
        <AbsoluteFill style={{ opacity: exA }}>
          <Words list={[{ s: "Useful", t: e.images }, { s: "frames,", t: e.images + 0.3 }]} t={t} x={80} y={130} px={56} />
          {EXTRACT_FRAMES.map((f, i) => {
            const fa = eo((t - (e.images + i * 0.2)) / 0.5);
            const x = 80 + i * 200;
            return (
              <div key={f.view} style={{ position: "absolute", left: x, top: 180 + (1 - fa) * 30, width: 180, opacity: fa }}>
                <div style={{ position: "relative", width: 180, height: 150, borderRadius: 14, overflow: "hidden", boxShadow: "0 0 0 1px rgba(255,255,255,0.25), 0 20px 40px rgba(0,0,0,0.5)" }}>
                  <Still src={f.src} frame={f.frame} />
                </div>
                <div style={{ fontFamily: FONT.film, fontWeight: 600, fontSize: 30, color: FILM.INK, marginTop: 10 }}>{f.view}</div>
                <div style={{ fontFamily: FONT.mono, fontSize: 28, color: FILM.GREY }}>{f.at}</div>
              </div>
            );
          })}
          <Words list={[{ s: "a", t: e.person - 0.25 }, { s: "person", t: e.person, fill: "grad" }, { s: "confirms.", t: e.confirm, fill: "grad" }]} t={t} x={80} y={520} px={56} />
          <Label x={82} y={590} px={30} weight={600} color={FILM.MINT} opacity={sm(e.confirm + 0.2, e.confirm + 0.6, t)}>
            ✓ Identity confirmed · Tag 001
          </Label>
        </AbsoluteFill>
      ) : null}
      {unA > 0 ? (
        <AbsoluteFill style={{ opacity: unA }}>
          <Label x={270} y={88} px={30} align="center" color={FILM.MINT}>
            Clear match
          </Label>
          <Label x={pose2.x} y={88} px={30} align="center" color="#ffb26b" opacity={enter}>
            Unclear
          </Label>
          <FloorShadow cx={pose2.x} cy={390 + 270} unit={190} />
          <Phone pose={pose2} light={{ ...light, ring: 0, spec: -1 }}>
            <UnclearScreen t={t} segments={UNCLEAR_SEGMENTS} t0={u.unclear} />
          </Phone>
          <Words list={[{ s: "No", t: u.guessing - 0.3 }, { s: "guessing.", t: u.guessing }]} t={t} x={820} y={380} px={56} />
          <Label x={822} y={440} px={30} weight={400} color={FILM.GREY} opacity={sm(u.stays, u.stays + 0.4, t)}>
            Stays unconfirmed
          </Label>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};


