import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Callout, Label, Words, cp, seq } from "../components/Type";
import { Footage, GRADE, pingPong } from "../components/Footage";
import { io, lerp, sm } from "../lib/h";
import { useT } from "../lib/time";
import { poseAt, toStage } from "../phone-track";
import { FILM } from "../theme";

// 00:22-00:38 Reveal: VEYRA wordmark, Identity / Monitoring / Insurance callouts, then the three promises.
const m = B.meet.cue;
const g = B.goal.cue;

/** corner header (>= 44 px), the reference's hook-shrinks-to-corner move */
export const CornerHeader: React.FC<{ text: string; t: number; t0: number; t1: number; color?: string }> = ({ text, t, t0, t1, color = FILM.INK }) => {
  const a = sm(t0, t0 + 0.5, t) * (1 - sm(t1 - 0.4, t1, t));
  if (a <= 0) return null;
  return (
    <Label x={56} y={82} px={44} weight={800} color={color} opacity={a * 0.92}>
      {text}
    </Label>
  );
};

export const RevealFront: React.FC = () => {
  const t = useT();
  const pose = poseAt(t);
  // wordmark: big at the reveal, then shrinks into the corner header as the camera orbits (goal beat)
  const k = io(sm(m.onePlace + 0.7, m.onePlace + 1.5, t));
  const px = lerp(132, 44, k);
  const X = lerp(96, 56, k),
    Y = lerp(330, 82, k);
  const wordFade = 1 - sm(B.herd.start - 0.3, B.herd.start + 0.2, t);
  const calloutFade = 1 - sm(m.onePlace + 0.5, m.onePlace + 1.0, t);
  // anchors on the Herd UI: tag column, alert pill, coverage pill
  const aTag = toStage(pose, 52, 276),
    aAlert = toStage(pose, 120, 492),
    aCov = toStage(pose, 330, 258);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: wordFade }}>
        <Words list={[{ s: "Meet", t: m.meet, fill: "grad" }]} t={t} x={X + 4} y={Y - px * 0.95} px={30} weight={600} alpha={1 - k} />
        <Words list={[{ s: "VEYRA", t: m.veyra }]} t={t} x={X} y={Y} px={px} weight={800} alpha={lerp(1, 0.92, k)} />
        <Label x={100} y={392} px={30} weight={400} color={FILM.GREY} opacity={sm(m.connects, m.connects + 0.5, t) * (1 - k)}>
          One app for every animal
        </Label>
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: calloutFade }}>
        <Callout pts={[aTag, [aTag[0] - 60, 480], [560, 480]]} p={cp(t, m.identity)} label="Identity" side="l" />
        <Callout pts={[aAlert, [aAlert[0] - 40, 560], [560, 560]]} p={cp(t, m.health)} label="Monitoring" side="l" />
        <Callout pts={[aCov, [aCov[0] + 60, 230], [1090, 230]]} p={cp(t, m.insurance)} label="Insurance" side="r" />
      </AbsoluteFill>
      {/* the three promises */}
      <AbsoluteFill style={{ opacity: 1 - sm(B.herd.start - 0.4, B.herd.start + 0.1, t) }}>
        <Words list={seq("Know every animal.", [g.know, g.know + 0.36, B.goal.cue.know + 0.78])} t={t} x={600} y={250} px={60} />
        <Words list={seq("Understand its value.", [g.value, g.value + 0.5, g.financial + 0.4])} t={t} x={600} y={345} px={60} fill={FILM.INK} />
        <Words list={[{ s: "Protect", t: g.protect, fill: "grad" }, { s: "it.", t: g.protect + 0.45, fill: "grad" }]} t={t} x={600} y={440} px={60} glow />
        <Label x={602} y={510} px={30} weight={400} color={FILM.GREY} opacity={sm(g.workflows, g.workflows + 0.5, t)}>
          With clearer, faster workflows
        </Label>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 00:38-00:46 Herd: the phone over the real barn (blurred), callouts on the rows.
const h = B.herd.cue;
export const HerdBack: React.FC = () => {
  const t = useT();
  const a = sm(B.herd.start - 0.3, B.herd.start + 0.8, t) * (1 - sm(B.capture.start - 0.2, B.capture.start + 0.4, t));
  return (
    <AbsoluteFill style={{ opacity: a * 0.85 }}>
      <Footage name="Barn backdrop" segments={pingPong("cctv", B.herd.start - 0.3, B.capture.start + 0.4, 2, 0.5)} frame={{ zoom: 1.3, fx: 0.5, fy: 0.4 }} filter={GRADE.backdrop} />
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(3,3,4,0.2) 0%, rgba(3,3,4,0.75) 60%, rgba(3,3,4,0.85) 100%)" }} />
    </AbsoluteFill>
  );
};

export const HerdFront: React.FC = () => {
  const t = useT();
  const pose = poseAt(t);
  const out = 1 - sm(B.capture.start - 0.3, B.capture.start + 0.2, t);
  const aTag = toStage(pose, 52, 276),
    aVal = toStage(pose, 320, 296),
    aCov = toStage(pose, 320, 342),
    aAl = toStage(pose, 90, 494);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <CornerHeader text="Herd dashboard" t={t} t0={h.herd} t1={B.capture.start} />
      <Callout pts={[aTag, [aTag[0] + 30, 170], [780, 170]]} p={cp(t, h.registered)} label="Ear tag ID" sub="Every registered animal" side="r" />
      <Callout pts={[aVal, [aVal[0] + 60, 290], [780, 290]]} p={cp(t, h.values)} label="Indicative value" sub="Estimated, in USD" side="r" />
      <Callout pts={[aCov, [aCov[0] + 80, 410], [780, 410]]} p={cp(t, h.status)} label="Insurance status" sub="Covered or not insured" side="r" />
      <Callout pts={[aAl, [aAl[0] + 160, 530], [780, 530]]} p={cp(t, h.alerts)} label="Alerts" sub="Camera observations to review" side="r" />
    </AbsoluteFill>
  );
};
