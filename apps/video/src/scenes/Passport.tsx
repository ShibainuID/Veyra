import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Callout, GradNumber, Label, Strike, Words, cp } from "../components/Type";
import { Sweep } from "../components/Sweep";
import { sm } from "../lib/h";
import { useT } from "../lib/time";
import { poseAt, toStage } from "../phone-track";
import { FILM } from "../theme";
import { SARI_VALUE, usd0 } from "../app-screens/data";

// 01:03-01:28 The passport is created in the app; its sections; the transparent valuation; not guaranteed.
const p = B.passport.cue;
const pp = B.passportPage.cue;
const v = B.valuation.cue;
const ng = B.notGuaranteed.cue;

export const PassportFront: React.FC = () => {
  const t = useT();
  const pose = poseAt(t);
  const headA = sm(p.digital - 0.1, p.digital + 0.3, t) * (1 - sm(pp.page - 0.3, pp.page + 0.1, t));
  const secA = 1 - sm(v.calculates - 0.4, v.calculates, t);
  const calcA = sm(v.calculates - 0.2, v.calculates + 0.3, t) * (1 - sm(B.gap.start - 0.3, B.gap.start + 0.1, t));
  // anchors on the passport sections (content y + shell 106, scroll 0)
  const aImg = toStage(pose, 70, 106 + 205),
    aAge = toStage(pose, 330, 106 + 342),
    aW = toStage(pose, 330, 106 + 376),
    aHist = toStage(pose, 120, 106 + 455),
    aDoc = toStage(pose, 150, 106 + 560);
  const lockT = v.range;
  return (
    <AbsoluteFill>
      <Sweep t={t} s0={B.passport.start - 0.25} s1={B.passport.start + 0.35} strength={0.55} />
      {/* headline while the passport builds */}
      {headA > 0 ? (
        <AbsoluteFill style={{ opacity: headA }}>
          <Words list={[{ s: "Digital", t: p.digital }]} t={t} x={80} y={260} px={72} />
          <Words list={[{ s: "Livestock", t: p.livestock }]} t={t} x={80} y={345} px={72} />
          <Words list={[{ s: "Passport.", t: p.passport, fill: "grad" }]} t={t} x={80} y={430} px={72} glow />
          <Label x={82} y={500} px={30} weight={400} color={FILM.GREY} opacity={sm(p.confirmed, p.confirmed + 0.4, t)}>
            Created in the app · Tag 001
          </Label>
        </AbsoluteFill>
      ) : null}
      {/* sections */}
      {t > pp.page - 0.3 && secA > 0 ? (
        <AbsoluteFill style={{ opacity: secA }}>
          <Callout pts={[aImg, [aImg[0] + 40, 130], [770, 130]]} p={cp(t, pp.identityImages)} label="Identity images" sub="Muzzle · teeth · body" side="r" />
          <Callout pts={[aAge, [aAge[0] + 60, 250], [770, 250]]} p={cp(t, pp.age)} label="Age 24–30 months" sub="Estimate" side="r" />
          <Callout pts={[aW, [aW[0] + 70, 370], [770, 370]]} p={cp(t, pp.weight)} label="Weight 480–560 kg" sub="Estimated, not guaranteed" side="r" subFill="#ffb26b" />
          <Callout pts={[aHist, [aHist[0] + 120, 490], [770, 490]]} p={cp(t, pp.history)} label="Observation history" side="r" />
          <Callout pts={[aDoc, [aDoc[0] + 120, 590], [770, 590]]} p={cp(t, pp.docs)} label="Supporting documents" side="r" />
        </AbsoluteFill>
      ) : null}
      {/* valuation calculator */}
      {calcA > 0 ? (
        <AbsoluteFill style={{ opacity: calcA }}>
          <Label x={600} y={150} px={30} weight={600} color={FILM.GREY} opacity={sm(v.calculates, v.calculates + 0.4, t)}>
            Indicative value range
          </Label>
          <Words list={[{ s: "480–560", t: v.weight }, { s: "kg", t: v.weight + 0.2, fill: FILM.GREY }]} t={t} x={600} y={250} px={64} />
          <Label x={600} y={292} px={28} weight={400} color={FILM.GREY} opacity={sm(v.weight + 0.3, v.weight + 0.7, t)}>
            confirmed weight
          </Label>
          <Words list={[{ s: "×", t: v.price - 0.15, fill: FILM.GREY }, { s: "5.20", t: v.price }, { s: "USD / kg", t: v.perKg, fill: FILM.GREY }]} t={t} x={600} y={380} px={64} />
          <Label x={600} y={422} px={28} weight={400} color={FILM.GREY} opacity={sm(v.perKg, v.perKg + 0.4, t)}>
            selected price per kilogram · 01 Oct 2026
          </Label>
          <div style={{ position: "absolute", left: 600, top: 452, width: 600 * sm(v.range, v.range + 0.5, t), height: 1, background: "rgba(255,255,255,0.35)" }} />
          <GradNumber x={600} y={540} px={76} text={`${usd0(SARI_VALUE[0])}–${usd0(SARI_VALUE[1])} USD`} opacity={sm(lockT - 0.1, lockT + 0.3, t)} glow={Math.exp(-Math.max(0, t - v.perKg - 0.1) * 3) * (t > v.perKg + 0.1 ? 1 : 0)} gleam={sm(v.perKg + 0.2, v.perKg + 0.9, t)} />
          {/* not guaranteed */}
          <Label x={602} y={598} px={30} weight={600} color="#ffb26b" opacity={sm(ng.transparent, ng.transparent + 0.4, t)}>
            Transparent estimate · not guaranteed
          </Label>
          <Label x={602} y={668} px={36} weight={600} color={FILM.INK} opacity={sm(ng.selling, ng.selling + 0.3, t)}>
            Selling price
          </Label>
          <Strike x0={596} x1={812} y={655} p={sm(ng.selling + 0.25, ng.selling + 0.6, t)} />
          <Label x={870} y={668} px={36} weight={600} color={FILM.INK} opacity={sm(ng.payout - 0.35, ng.payout, t)}>
            Insurance payout
          </Label>
          <Strike x0={864} x1={1150} y={655} p={sm(ng.payout, ng.payout + 0.35, t)} />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
