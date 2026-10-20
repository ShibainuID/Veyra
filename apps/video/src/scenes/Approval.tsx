import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { GradNumber, Label, Words } from "../components/Type";
import { clamp, eo, sm } from "../lib/h";
import { useT } from "../lib/time";
import { FILM, FONT } from "../theme";
import { INSURED_VALUE, PREMIUM, RECEIPTS, WALLET_AFTER, WALLET_BEFORE, usd } from "../app-screens/data";

// 01:51-02:13 The agent prepares two separate actions; the manager approves each; sandbox; distinct states.
const pr = B.prepare.cue;
const ar = B.approvalRule.cue;
const ap = B.approve.cue;
const sb = B.sandbox.cue;
const ac = B.activation.cue;

const Glass: React.FC<{ x: number; y: number; w: number; h: number; a: number; children: React.ReactNode }> = ({ x, y, w, h, a, children }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y + (1 - a) * 24,
      width: w,
      height: h,
      opacity: a,
      borderRadius: 18,
      background: "rgba(22,23,30,0.94)",
      boxShadow: "0 0 0 1px rgba(255,255,255,0.16), 0 24px 50px rgba(0,0,0,0.5)",
      padding: "18px 22px",
      boxSizing: "border-box",
      color: FILM.INK,
      fontFamily: FONT.film,
    }}
  >
    {children}
  </div>
);

const StampBox: React.FC<{ t: number; at: number }> = ({ t, at }) => {
  const done = t >= at;
  const p = done ? eo(clamp((t - at) / 0.18)) : 0;
  return (
    <div
      style={{
        display: "inline-flex",
        marginTop: 12,
        padding: "4px 12px",
        border: done ? "5px double #7cf0b8" : "2px dashed #f2c94c",
        borderRadius: 5,
        color: done ? "#7cf0b8" : "#f2c94c",
        fontFamily: FONT.mono,
        fontWeight: 700,
        fontSize: 28,
        letterSpacing: "0.04em",
        scale: String(done ? 1.06 - 0.06 * p : 1),
        opacity: done ? 0.35 + 0.65 * p : 1,
      }}
    >
      {done ? "APPROVED · 09:31 · W.S." : "AWAITING YOUR STAMP"}
    </div>
  );
};

const Step: React.FC<{ y: number; t: number; at: number; label: string; sub: string; on: boolean; waiting?: boolean }> = ({ y, t, at, label, sub, on, waiting }) => {
  const a = eo((t - at) / 0.4);
  const color = on ? FILM.MINT : waiting ? "#f2c94c" : FILM.INK;
  return (
    <div style={{ position: "absolute", left: 640, top: y + (1 - a) * 16, opacity: a, display: "flex", gap: 20, alignItems: "center" }}>
      <div
        style={{
          width: 46,
          height: 46,
          borderRadius: 23,
          border: on ? "none" : `2px dashed ${color}`,
          background: on ? FILM.MINT : "transparent",
          display: "grid",
          placeItems: "center",
          color: "#062b1a",
          fontWeight: 800,
          fontSize: 26,
          fontFamily: FONT.film,
          flex: "none",
        }}
      >
        {on ? "✓" : ""}
      </div>
      <div>
        <div style={{ fontFamily: FONT.film, fontWeight: 700, fontSize: 36, letterSpacing: -1, color }}>{label}</div>
        <div style={{ fontFamily: FONT.mono, fontSize: 28, color: FILM.GREY }}>{sub}</div>
      </div>
    </div>
  );
};

export const ApprovalFront: React.FC = () => {
  const t = useT();
  const cardsA = 1 - sm(sb.sandbox - 0.5, sb.sandbox - 0.1, t);
  const aA = sm(pr.application - 0.1, pr.application + 0.4, t);
  const bA = sm(pr.payment - 0.1, pr.payment + 0.4, t);
  const sbA = sm(sb.sandbox - 0.1, sb.sandbox + 0.3, t) * (1 - sm(ac.payment - 0.5, ac.payment - 0.1, t));
  const railA = sm(ac.payment - 0.3, ac.payment, t) * (1 - sm(B.cameras.start + 0.05, B.cameras.start + 0.5, t));
  const confirmed = t >= ac.confirms;
  return (
    <AbsoluteFill>
      {cardsA > 0 ? (
        <AbsoluteFill style={{ opacity: cardsA }}>
          <Words list={[{ s: "Approval", t: ar.approval, fill: "grad" }, { s: "first.", t: ar.approval + 0.3 }]} t={t} x={640} y={112} px={56} glow />
          <Glass x={640} y={160} w={570} h={220} a={aA}>
            <div style={{ fontWeight: 700, fontSize: 36, letterSpacing: -1 }}>Policy application</div>
            <div style={{ fontSize: 28, color: FILM.GREY, marginTop: 4 }}>Auto-filled from the passport</div>
            <div style={{ fontFamily: FONT.mono, fontSize: 28, marginTop: 4 }}>{usd(INSURED_VALUE)} USD insured</div>
            <StampBox t={t} at={ap.approves} />
          </Glass>
          <Glass x={640} y={400} w={570} h={236} a={bA}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontWeight: 700, fontSize: 36, letterSpacing: -1 }}>Premium payment</div>
              <div style={{ fontSize: 28, color: FILM.GREY }}>separate</div>
            </div>
            <div style={{ position: "relative", height: 76 }}>
              <GradNumber x={0} y={68} px={64} text={`${usd(PREMIUM)} USD`} />
            </div>
            <StampBox t={t} at={ap.each} />
          </Glass>
          <Label x={642} y={680} px={28} weight={600} color={FILM.MINT} opacity={sm(ap.response, ap.response + 0.4, t)} mono>
            Test provider: received · {RECEIPTS.application}
          </Label>
        </AbsoluteFill>
      ) : null}
      {sbA > 0 ? (
        <AbsoluteFill style={{ opacity: sbA }}>
          <div
            style={{
              position: "absolute",
              left: 640,
              top: 200,
              padding: "8px 28px",
              border: "3px dashed rgba(255,255,255,0.8)",
              borderRadius: 14,
              fontFamily: FONT.mono,
              fontWeight: 700,
              fontSize: 64,
              letterSpacing: "0.08em",
              color: FILM.INK,
              opacity: eo((t - sb.sandbox) / 0.4),
            }}
          >
            SANDBOX
          </div>
          <Words list={[{ s: "No", t: sb.money - 0.15 }, { s: "real", t: sb.money }, { s: "money.", t: sb.money + 0.25 }]} t={t} x={640} y={420} px={64} />
          <Label x={642} y={490} px={30} mono weight={400} color={FILM.GREY} opacity={sm(sb.money + 0.2, sb.money + 0.6, t)}>
            Wallet {usd(WALLET_BEFORE)} → {usd(WALLET_AFTER)} USD
          </Label>
        </AbsoluteFill>
      ) : null}
      {railA > 0 ? (
        <AbsoluteFill style={{ opacity: railA }}>
          <Step y={150} t={t} at={ac.payment - 0.25} label="Submitted" sub={RECEIPTS.application} on />
          <Step y={290} t={t} at={ac.payment} label="Payment recorded" sub={`Sandbox · ${RECEIPTS.payment}`} on />
          <Step
            y={430}
            t={t}
            at={ac.notMean}
            label={confirmed ? "Coverage confirmed" : "Coverage: waiting"}
            sub={confirmed ? `By the insurer · ${RECEIPTS.policy}` : "Only the insurer can confirm"}
            on={confirmed}
            waiting
          />
          <div style={{ position: "absolute", left: 662, top: 196, width: 2, height: 94 + 140 * sm(ac.notMean, ac.notMean + 0.4, t), background: "rgba(255,255,255,0.25)" }} />
          <Words list={[{ s: "Coverage", t: ac.confirms + 0.15, fill: "grad" }, { s: "active.", t: ac.confirms + 0.4, fill: "grad" }]} t={t} x={640} y={640} px={64} glow />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
