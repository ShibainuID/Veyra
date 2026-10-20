import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Footage, GRADE, pingPong } from "../components/Footage";
import { Stage } from "../components/Stage";
import { Label, Words, seq } from "../components/Type";
import { clamp, eo, io, lerp, sm } from "../lib/h";
import { useT } from "../lib/time";
import { FILM, FONT } from "../theme";

// 00:00-00:22 Problem: real herd -> the cow side-on -> scattered records / footage / documents -> too long.
const hook = B.hook.cue;
const sc = B.scattered.cue;
const tl = B.tooLong.cue;
const T_SHRINK = B.scattered.start - 0.1; // footage shrinks into a card on the stage
const T_WORKER = B.tooLong.start - 0.15; // back to full-frame footage

// A card on the stage: rounded, hairline rim, soft shadow, slightly blurred when far away
const Card: React.FC<{ x: number; y: number; w: number; h: number; a: number; rot?: number; blur?: number; children: React.ReactNode; label?: string; la?: number }> = ({
  x,
  y,
  w,
  h,
  a,
  rot = 0,
  blur = 0,
  children,
  label,
  la = 1,
}) => (
  <div style={{ position: "absolute", left: x - w / 2, top: y - h / 2, width: w, height: h, opacity: a, rotate: `${rot}deg`, filter: blur > 0.3 ? `blur(${blur}px)` : undefined }}>
    <div style={{ position: "absolute", inset: 0, borderRadius: 18, overflow: "hidden", boxShadow: "0 30px 60px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.18)" }}>{children}</div>
    {label ? (
      <Label x={w / 2} y={h + 46} px={30} align="center" opacity={la}>
        {label}
      </Label>
    ) : null}
  </div>
);

const PaperRecords: React.FC = () => (
  <AbsoluteFill style={{ background: "#efe7d6", padding: 22, fontFamily: FONT.mono, color: "#3b352c" }}>
    <div style={{ fontFamily: FONT.film, fontWeight: 600, fontSize: 19, borderBottom: "2px solid #8b7f6a", paddingBottom: 8 }}>Herd book · Pen A</div>
    {["004  weighed ? kg", "002  vaccinated 12/09", "006  moved → Pen C", "001  (no tag yet)", "003  calving due ?"].map((l, i) => (
      <div key={i} style={{ fontSize: 17, padding: "9px 0", borderBottom: "1px solid #c9bda6", rotate: `${(i % 2 ? -0.6 : 0.5).toFixed(1)}deg` }}>
        {l}
      </div>
    ))}
  </AbsoluteFill>
);

const PolicyDoc: React.FC = () => (
  <AbsoluteFill style={{ background: "#fafafa", padding: 22, fontFamily: FONT.film, color: "#222" }}>
    <div style={{ fontWeight: 800, fontSize: 19 }}>Livestock policy schedule</div>
    <div style={{ fontSize: 14, color: "#777", marginTop: 4 }}>Scanned PDF · page 3 of 14</div>
    {[0.92, 0.7, 0.85, 0.6, 0.88, 0.74, 0.5].map((w, i) => (
      <div key={i} style={{ height: 9, width: `${w * 100}%`, background: "#d9d9de", borderRadius: 4, marginTop: 15 }} />
    ))}
    <div style={{ position: "absolute", right: 20, bottom: 18, border: "3px solid #c0392b", color: "#c0392b", fontWeight: 800, fontSize: 15, padding: "2px 8px", rotate: "-6deg", opacity: 0.8 }}>
      ANIMAL ID?
    </div>
  </AbsoluteFill>
);

export const ProblemBack: React.FC = () => {
  const t = useT();
  const fadeIn = sm(0, 0.5, t);
  const shrink = io(sm(T_SHRINK, T_SHRINK + 1.1, t));
  const back = sm(T_WORKER, T_WORKER + 0.8, t);
  const toBlack = 1 - sm(B.meet.start - 0.55, B.meet.start - 0.05, t);
  // shot 1+2 sit in a frame that shrinks into the "camera footage" card
  const fw = lerp(1280, 400, shrink),
    fh = lerp(720, 225, shrink);
  const drift = sm(sc.scattered, sc.scattered + 2.2, t);
  const fx = lerp(640, lerp(640, 770, drift), shrink),
    fy = lerp(360, lerp(360, 330, drift), shrink);
  return (
    <AbsoluteFill style={{ background: "#000", opacity: toBlack }}>
      <Stage light={{ cx: 640, cy: 600, unit: 220, key: 0.7 * shrink * (1 - back) }} t={t} />
      {/* shot 1: the herd in the barn (CCTV wide); shot 2: the cow side-on */}
      {t < T_WORKER + 0.8 ? (
        <div
          style={{
            position: "absolute",
            left: fx - fw / 2,
            top: fy - fh / 2,
            width: fw,
            height: fh,
            borderRadius: 18 * shrink,
            overflow: "hidden",
            opacity: fadeIn * (1 - back),
            boxShadow: shrink > 0.01 ? `0 30px 60px rgba(0,0,0,${0.55 * shrink}), 0 0 0 1px rgba(255,255,255,${0.18 * shrink})` : undefined,
            rotate: `${(1.5 * drift).toFixed(2)}deg`,
          }}
        >
          {t < hook.everyCow + 0.05 ? (
            <Footage
              name="Herd wide"
              segments={[{ clip: "cctv", start: 0, end: hook.everyCow, from: 0.2, rate: 0.6 }]}
              frame={{ zoom: lerp(1.25, 1.45, t / 2.2), fx: 0.32, fy: 0.3 }}
              filter={GRADE.film}
            />
          ) : (
            <Footage
              name="Cow side-on"
              segments={[{ clip: "hp", start: hook.everyCow, end: T_WORKER + 0.8, from: 5.0, rate: 0.35 }]}
              frame={{ zoom: lerp(1.12, 1.22, sm(hook.everyCow, T_SHRINK, t)), fx: 0.45, fy: 0.55 }}
              filter={shrink > 0.5 ? GRADE.cctv : GRADE.film}
            />
          )}
          {/* REC chip once it is "camera footage" */}
          <div style={{ position: "absolute", left: 14, top: 12, opacity: sm(sc.camera, sc.camera + 0.3, t), display: "flex", gap: 8, alignItems: "center", fontFamily: FONT.mono, color: "#fff", fontSize: 15, fontWeight: 700 }}>
            <span style={{ width: 11, height: 11, borderRadius: 6, background: FILM.RED }} /> CAM-01
          </div>
        </div>
      ) : null}
      {/* shot 3: worker leading the cow, from the barn camera, close crop */}
      {t > T_WORKER - 0.05 ? (
        <AbsoluteFill style={{ opacity: back }}>
          <Footage
            name="Worker and cow"
            segments={pingPong("cctv", T_WORKER, B.meet.start, 1.0, 0.55)}
            frame={{ zoom: lerp(2.1, 2.35, sm(T_WORKER, B.meet.start, t)), fx: 0.47, fy: 0.52 }}
            filter={GRADE.dark}
          />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

export const ProblemFront: React.FC = () => {
  const t = useT();
  const shrink = io(sm(T_SHRINK, T_SHRINK + 1.1, t));
  const back = sm(T_WORKER, T_WORKER + 0.8, t);
  const toBlack = 1 - sm(B.meet.start - 0.55, B.meet.start - 0.05, t);
  const drift = sm(sc.scattered, sc.scattered + 2.2, t);
  const hookFade = 1 - sm(T_SHRINK - 0.2, T_SHRINK + 0.4, t);
  const cardsOut = 1 - back;
  // the three fragments
  const rec = sm(sc.records, sc.records + 0.5, t);
  const ins = sm(sc.insurance, sc.insurance + 0.5, t);
  const camLab = sm(sc.camera, sc.camera + 0.5, t);
  // broken hairlines between fragments (they never join)
  const lines = sm(sc.insurance + 0.5, sc.insurance + 1.3, t) * cardsOut;
  // too long: Evidence? -> ... -> Action
  const ev = sm(tl.evidence, tl.evidence + 0.5, t);
  const ac = sm(tl.action, tl.action + 0.5, t);
  const path = io(sm(tl.evidence + 0.2, tl.tooLong + 0.8, t));
  const wrong = t - tl.wrong;
  return (
    <AbsoluteFill style={{ opacity: toBlack }}>
      {/* hook headline */}
      <AbsoluteFill style={{ opacity: hookFade }}>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 300, background: "linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,0.65))" }} />
        <Words list={seq("Every cow.", [hook.everyCow, hook.cow])} t={t} x={80} y={560} px={88} />
        <Words list={[{ s: "A", t: hook.valuable - 0.12 }, { s: "valuable", t: hook.valuable, fill: "grad" }, { s: "asset.", t: hook.asset, fill: "grad" }]} t={t} x={80} y={650} px={72} glow />
      </AbsoluteFill>
      {/* scattered */}
      {shrink > 0 && cardsOut > 0 ? (
        <AbsoluteFill style={{ opacity: cardsOut }}>
          <Words list={[{ s: "Scattered.", t: sc.scattered }]} t={t} x={640} y={118} px={64} align="center" />
          <Card x={lerp(640, 300, drift)} y={lerp(380, 400, drift)} w={260} h={300} a={rec} rot={-4 * drift - 2} label="Paper records" la={rec}>
            <PaperRecords />
          </Card>
          <Label x={lerp(640, 770, drift)} y={lerp(360, 330, drift) + 112 + 46} px={30} align="center" opacity={camLab * shrink}>
            Camera footage
          </Label>
          <Card x={lerp(900, 1060, ins)} y={lerp(420, 440, ins)} w={240} h={300} a={ins} rot={5 * ins} label="Insurance documents" la={ins}>
            <PolicyDoc />
          </Card>
          <svg width={1280} height={720} style={{ position: "absolute", inset: 0, opacity: lines }}>
            {[
              [430, 390, 560, 360],
              [980, 360, 940, 360],
            ].map(([x0, y0, x1, y1], i) => (
              <g key={i}>
                <line x1={x0} y1={y0} x2={x0 + (x1 - x0) * 0.42} y2={y0 + (y1 - y0) * 0.42} stroke="rgba(255,255,255,0.45)" strokeWidth={1.2} strokeDasharray="5 6" />
                <line x1={x0 + (x1 - x0) * 0.62} y1={y0 + (y1 - y0) * 0.62} x2={x1} y2={y1} stroke="rgba(255,255,255,0.45)" strokeWidth={1.2} strokeDasharray="5 6" />
                <circle cx={x0 + (x1 - x0) * 0.52} cy={y0 + (y1 - y0) * 0.52} r={5} fill="none" stroke={FILM.RED} strokeWidth={1.6} />
              </g>
            ))}
          </svg>
        </AbsoluteFill>
      ) : null}
      {/* too long */}
      {back > 0 ? (
        <AbsoluteFill style={{ opacity: back }}>
          {/* a red pulse where something is wrong */}
          {wrong > 0 ? (
            <div
              style={{
                position: "absolute",
                left: 700 - 70 - 60 * eo(clamp((wrong % 1.6) / 1.2)),
                top: 360 - 70 - 60 * eo(clamp((wrong % 1.6) / 1.2)),
                width: 140 + 120 * eo(clamp((wrong % 1.6) / 1.2)),
                height: 140 + 120 * eo(clamp((wrong % 1.6) / 1.2)),
                borderRadius: "50%",
                border: `2px solid ${FILM.RED}`,
                opacity: (1 - clamp((wrong % 1.6) / 1.2)) * 0.9 * (1 - sm(tl.tooLong, tl.tooLong + 0.4, t)),
              }}
            />
          ) : null}
          <Label x={120} y={200} px={44} weight={800} opacity={ev}>
            Evidence?
          </Label>
          <Label x={1160} y={200} px={44} weight={800} align="right" opacity={ac}>
            Action
          </Label>
          <svg width={1280} height={720} style={{ position: "absolute", inset: 0 }}>
            <path
              d="M330 186 C 420 300, 520 120, 610 230 S 780 120, 860 240 S 960 150, 980 186"
              fill="none"
              stroke="rgba(255,255,255,0.75)"
              strokeWidth={1.4}
              strokeDasharray={`${path * 900} 2000`}
            />
          </svg>
          <Words list={[{ s: "Too", t: tl.tooLong, fill: FILM.RED }, { s: "long.", t: tl.tooLong + 0.45, fill: FILM.RED }]} t={t} x={640} y={600} px={104} align="center" />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
