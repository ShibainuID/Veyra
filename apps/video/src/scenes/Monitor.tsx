import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { CctvView } from "../components/Cctv";
import { Callout, Label, Strike, Words, cp } from "../components/Type";
import { Sweep } from "../components/Sweep";
import { eo, lerp, sm } from "../lib/h";
import { useT } from "../lib/time";
import { FILM, FONT } from "../theme";
import { CCTV_SEGMENTS, CCTV_START } from "../footage-plan";
import { EarTag } from "../app-screens/ui";

// 02:13-02:35 Farm CCTV observes; only the associated track carries an ID; reduced movement -> review, not diagnosis.
const cm = B.cameras.cue;
const tk = B.tracks.cue;
const al = B.alert.cue;
const nd = B.notDiagnosis.cue;
const ASSOC = tk.tracks + 0.6;

// a forward-only HUD clock for the recorded replay: 17:09:10 at the start of the clip
const clock = (t: number) => {
  const s = Math.floor(17 * 3600 + 9 * 60 + 10 + Math.max(0, t - CCTV_START) * 0.395);
  const f = (n: number) => String(n).padStart(2, "0");
  return `20 OCT 2026 · ${f(Math.floor(s / 3600))}:${f(Math.floor((s % 3600) / 60))}:${f(s % 60)}`;
};

export const MonitorBack: React.FC = () => {
  const t = useT();
  const a = sm(B.cameras.start - 0.05, B.cameras.start + 0.5, t);
  const dimP = sm(nd.inspect - 1.0, nd.inspect - 0.2, t);
  return (
    <AbsoluteFill style={{ opacity: a * lerp(1, 0.4, dimP), filter: dimP > 0.01 ? `blur(${(10 * dimP).toFixed(1)}px)` : undefined }}>
      <CctvView t={t} segments={CCTV_SEGMENTS} zoneAt={tk.recorded} detectAt={tk.tracks} assocAt={ASSOC} highlightRed={al.alert} clock={clock} hud={dimP < 0.5} />
    </AbsoluteFill>
  );
};

const Panel: React.FC<{ x: number; y: number; w: number; h: number; a: number; children: React.ReactNode }> = ({ x, y, w, h, a, children }) => (
  <div style={{ position: "absolute", left: x, top: y + (1 - a) * 16, width: w, height: h, opacity: a, borderRadius: 16, background: "rgba(10,11,16,0.82)", boxShadow: "0 0 0 1px rgba(255,255,255,0.16)", padding: "16px 20px", boxSizing: "border-box", color: FILM.INK, fontFamily: FONT.film }}>
    {children}
  </div>
);

const TREND = [0.8, 0.86, 0.76, 0.84, 0.79, 0.82, 0.31];

export const MonitorFront: React.FC = () => {
  const t = useT();
  const out = 1 - sm(nd.inspect - 1.0, nd.inspect - 0.4, t);
  const pass = sm(cm.passport, cm.passport + 0.4, t) * (1 - sm(tk.tracks - 0.3, tk.tracks, t));
  const assoc = sm(ASSOC, ASSOC + 0.4, t) * (1 - sm(al.identified + 0.3, al.identified + 0.7, t));
  const chartA = sm(al.identified, al.identified + 0.5, t);
  const drop = sm(al.less, al.less + 0.6, t);
  const alertA = sm(al.alert, al.alert + 0.4, t);
  // chart geometry
  const cx0 = 70,
    cx1 = 490,
    cy0 = 470,
    cy1 = 380;
  const pts = TREND.map((v, i) => {
    const vv = i === TREND.length - 1 ? lerp(0.8, v, drop) : v;
    return [lerp(cx0, cx1, i / (TREND.length - 1)), lerp(cy0 + 100, cy1 + 40, vv)] as const;
  });
  const shownN = Math.max(2, Math.round(lerp(2, TREND.length, eo((t - al.identified) / 1.2))));
  const path = pts.slice(0, shownN).map((q, i) => `${i ? "L" : "M"}${q[0]},${q[1]}`).join(" ");
  const last = pts[TREND.length - 1];
  const inspA = sm(nd.inspect, nd.inspect + 0.4, t) * (1 - sm(B.ask.start - 0.3, B.ask.start + 0.1, t));
  return (
    <AbsoluteFill>
      <Sweep t={t} s0={B.cameras.start} s1={B.cameras.start + 0.6} strength={0.35} />
      <AbsoluteFill style={{ opacity: out }}>
        {/* the passport the camera observations will attach to */}
        {pass > 0 ? (
          <>
            <div style={{ position: "absolute", left: 40, top: 560, display: "flex", alignItems: "center", gap: 16, padding: "12px 18px", borderRadius: 14, background: "rgba(10,11,16,0.82)", boxShadow: "0 0 0 1px rgba(255,255,255,0.16)", opacity: pass }}>
              <EarTag num="001" h={52} />
              <div style={{ fontFamily: FONT.film, color: FILM.INK }}>
                <div style={{ fontWeight: 700, fontSize: 30 }}>Sari · Passport</div>
                <div style={{ fontSize: 28, color: FILM.GREY }}>animal-demo-001</div>
              </div>
            </div>
            <Callout pts={[[200, 556], [200, 150], [240, 112]]} p={cp(t, cm.camera)} label="Linked to camera observations" side="r" />
          </>
        ) : null}
        {assoc > 0 ? (
          <div style={{ position: "absolute", left: 40, top: 560, padding: "14px 20px", borderRadius: 14, background: "rgba(10,11,16,0.82)", boxShadow: "0 0 0 1px rgba(255,255,255,0.16)", opacity: assoc, fontFamily: FONT.film, color: FILM.INK }}>
            <div style={{ fontWeight: 700, fontSize: 30, color: "#f2c94c" }}>Identified in scan zone · 31 points</div>
            <div style={{ fontSize: 28, color: FILM.GREY, marginTop: 2, opacity: sm(tk.lastKnown, tk.lastKnown + 0.4, t) }}>Last seen 17:09 · Pen A · feed line</div>
            <div style={{ fontSize: 28, color: FILM.GREY }}>Other tracks: no tag, unassigned</div>
          </div>
        ) : null}
        {chartA > 0 ? (
          <Panel x={40} y={300} w={480} h={290} a={chartA}>
            <div style={{ fontWeight: 700, fontSize: 30 }}>Movement · 001 Sari</div>
            <div style={{ fontSize: 28, color: FILM.GREY }}>vs earlier replay windows</div>
            <svg width={1280} height={720} style={{ position: "absolute", left: -40, top: -300, overflow: "visible" }}>
              <line x1={cx0} x2={cx1} y1={lerp(cy0 + 100, cy1 + 40, 0.66)} y2={lerp(cy0 + 100, cy1 + 40, 0.66)} stroke="rgba(255,255,255,0.4)" strokeWidth={1.2} strokeDasharray="6 6" />
              <defs>
                <linearGradient id="mv" x1="0" x2="1">
                  <stop offset="0" stopColor="#b69cff" />
                  <stop offset="0.5" stopColor="#e879f9" />
                  <stop offset="1" stopColor="#ff9a4d" />
                </linearGradient>
              </defs>
              <path d={path} fill="none" stroke="url(#mv)" strokeWidth={3} strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 8px rgba(232,121,249,0.7))" }} />
              {shownN >= TREND.length ? <circle cx={last[0]} cy={last[1]} r={7 + 5 * drop} fill={drop > 0.5 ? "#ffb26b" : "#fff"} /> : null}
            </svg>
            <div style={{ position: "absolute", right: 20, bottom: 14, fontSize: 28, color: drop > 0.5 ? "#ffb26b" : FILM.GREY, fontWeight: 600, opacity: drop }}>Moving less</div>
          </Panel>
        ) : null}
        {alertA > 0 ? (
          <Panel x={760} y={80} w={480} h={230} a={alertA}>
            <div style={{ fontWeight: 700, fontSize: 30, color: "#ffb26b", lineHeight: 1.1 }}>⚠ Unusual reduced movement</div>
            <div style={{ fontSize: 28, marginTop: 6 }}>Review required</div>
            <div style={{ fontFamily: FONT.mono, fontSize: 30, marginTop: 6, opacity: sm(al.timestamp, al.timestamp + 0.3, t) }}>17:02–17:09</div>
            <div style={{ position: "absolute", right: 18, bottom: 18, width: 150, height: 84, borderRadius: 10, overflow: "hidden", boxShadow: "0 0 0 2px #ffb26b", opacity: sm(al.footage, al.footage + 0.4, t) }}>
              <CctvView t={t} segments={CCTV_SEGMENTS} hud={false} assocAt={-1} highlightRed={-1} frame={{ zoom: 2.2, fx: 0.58, fy: 0.62 }} name="Alert clip" ui={0.4} />
            </div>
            <div style={{ position: "absolute", left: 20, bottom: 18, fontSize: 28, color: FILM.GREY, opacity: sm(al.footage, al.footage + 0.4, t) }}>clip →</div>
          </Panel>
        ) : null}
      </AbsoluteFill>
      {/* not a diagnosis */}
      {inspA > 0 ? (
        <AbsoluteFill style={{ opacity: inspA }}>
          <Words list={[{ s: "Requires", t: nd.inspect - 0.25 }, { s: "inspection.", t: nd.inspect, fill: "grad" }]} t={t} x={80} y={300} px={60} glow />
          <Label x={82} y={400} px={44} weight={600} color={FILM.INK} opacity={sm(nd.not, nd.not + 0.3, t)}>
            Medical diagnosis
          </Label>
          <Strike x0={76} x1={466} y={386} p={sm(nd.diagnosis, nd.diagnosis + 0.35, t)} />
          <Label x={82} y={460} px={28} weight={400} color={FILM.GREY} opacity={sm(nd.diagnosis + 0.3, nd.diagnosis + 0.7, t)}>
            A reason to look, not a conclusion
          </Label>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
