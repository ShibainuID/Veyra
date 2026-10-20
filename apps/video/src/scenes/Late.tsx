import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Footage, GRADE, pingPong } from "../components/Footage";
import { GradNumber, Label, Words } from "../components/Type";
import { Sweep } from "../components/Sweep";
import { clamp, eo, io, lerp, sm } from "../lib/h";
import { useT } from "../lib/time";
import { poseAt } from "../phone-track";
import { FILM, FONT } from "../theme";
import { RECEIPTS } from "../app-screens/data";
import { EarTag } from "../app-screens/ui";

const ask = B.ask.cue;
const inc = B.incident.cue;
const ch = B.checklist.cue;
const mi = B.missing.cue;
const su = B.submit.cue;
const au = B.audit.cue;
const bl = B.blocks.cue;
const cn = B.connects.cue;
const tg = B.tagline.cue;

// ---------------- 02:35-02:43 Ask ----------------
export const AskFront: React.FC = () => {
  const t = useT();
  const a1 = sm(ask.ask, ask.ask + 0.4, t) * (1 - sm(ask.answer - 0.3, ask.answer, t));
  const a2 = sm(ask.answer, ask.answer + 0.4, t) * (1 - sm(B.incident.start - 0.3, B.incident.start + 0.1, t));
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: a1 }}>
        <Words list={[{ s: "Ask.", t: ask.ask }]} t={t} x={80} y={320} px={72} />
        <Label x={82} y={380} px={30} weight={400} color={FILM.GREY} opacity={sm(ask.question, ask.question + 0.4, t)}>
          In plain words, in the app
        </Label>
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: a2 }}>
        <Label x={80} y={220} px={30} weight={600} color={FILM.GREY}>
          Last seen
        </Label>
        <GradNumber x={76} y={330} px={104} text="17:09" glow={Math.exp(-Math.max(0, t - ask.answer) * 3)} gleam={sm(ask.answer + 0.3, ask.answer + 1.0, t)} />
        <Label x={80} y={400} px={30} weight={600} mono>
          CAM-01 · Pen A · feed line
        </Label>
        <Label x={80} y={456} px={28} weight={400} color={FILM.GREY} opacity={sm(ask.recorded, ask.recorded + 0.4, t)}>
          From recorded observations
        </Label>
        <Label x={80} y={494} px={28} weight={400} color={FILM.GREY} opacity={sm(ask.recorded + 0.2, ask.recorded + 0.6, t)}>
          not a live location
        </Label>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------- 02:43-03:08 Claim for the insured cow ----------------
export const ClaimBack: React.FC = () => {
  const t = useT();
  const a = sm(B.incident.start - 0.4, B.incident.start + 0.4, t) * (1 - sm(ch.gathers - 0.3, ch.gathers + 0.5, t));
  return (
    <AbsoluteFill style={{ opacity: a }}>
      {/* Bima: a different cow, in the same barn (CCTV, tight crop) */}
      <Footage name="Bima in the barn" segments={pingPong("cctv", B.incident.start - 0.4, ch.gathers + 0.5, 0.4, 0.45, 0.2, 3.2)} frame={{ zoom: 1.9, fx: 0.62, fy: 0.3 }} filter="contrast(1.05) saturate(0.85) brightness(0.62)" />
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(3,3,4,0.35) 0%, rgba(3,3,4,0.45) 45%, rgba(3,3,4,0.82) 62%, rgba(3,3,4,0.9) 100%)" }} />
    </AbsoluteFill>
  );
};

const Row: React.FC<{ y: number; t: number; at: number; label: string; sub: string; state: "ok" | "missing" }> = ({ y, t, at, label, sub, state }) => {
  const a = eo((t - at) / 0.35);
  const col = state === "ok" ? FILM.MINT : "#ffb26b";
  return (
    <div style={{ position: "absolute", left: 640, top: y + (1 - a) * 12, opacity: a, display: "flex", gap: 18, alignItems: "flex-start" }}>
      <div style={{ width: 40, height: 40, borderRadius: 20, background: state === "ok" ? col : "transparent", border: state === "ok" ? "none" : `2px solid ${col}`, display: "grid", placeItems: "center", color: state === "ok" ? "#062b1a" : col, fontWeight: 800, fontSize: 24, fontFamily: FONT.film, flex: "none", marginTop: 2 }}>
        {state === "ok" ? "✓" : "!"}
      </div>
      <div>
        <div style={{ fontFamily: FONT.film, fontWeight: 700, fontSize: 34, letterSpacing: -0.8, color: state === "ok" ? FILM.INK : col }}>{label}</div>
        <div style={{ fontFamily: FONT.film, fontSize: 28, color: FILM.GREY }}>{sub}</div>
      </div>
    </div>
  );
};

const StampBig: React.FC<{ x: number; y: number; t: number; at: number; text: string; color?: string }> = ({ x, y, t, at, text, color = "#7cf0b8" }) => {
  if (t < at) return null;
  const p = eo(clamp((t - at) / 0.18));
  return (
    <div style={{ position: "absolute", left: x, top: y, padding: "6px 14px", border: `5px double ${color}`, borderRadius: 5, color, fontFamily: FONT.mono, fontWeight: 700, fontSize: 30, letterSpacing: "0.04em", scale: String(1.06 - 0.06 * p), opacity: 0.35 + 0.65 * p, transformOrigin: "left center" }}>
      {text}
    </div>
  );
};

export const ClaimFront: React.FC = () => {
  const t = useT();
  const pose = poseAt(t);
  const incA = sm(inc.later, inc.later + 0.4, t) * (1 - sm(ch.gathers - 0.3, ch.gathers, t));
  const listA = sm(ch.gathers - 0.1, ch.gathers + 0.3, t) * (1 - sm(su.facts - 0.6, su.facts - 0.2, t));
  const vetOk = t >= mi.submission + 0.45;
  const subA = sm(su.facts - 0.3, su.facts + 0.2, t) * (1 - sm(B.audit.start - 0.3, B.audit.start + 0.1, t));
  const arrow = sm(su.send, su.send + 0.8, t);
  const x0 = pose.x - 175,
    x1 = 520;
  return (
    <AbsoluteFill>
      {incA > 0 ? (
        <AbsoluteFill style={{ opacity: incA }}>
          <Label x={720} y={200} px={30} weight={600} color={FILM.GREY}>
            Already insured
          </Label>
          <div style={{ position: "absolute", left: 720, top: 226, display: "flex", alignItems: "center", gap: 18 }}>
            <EarTag num="002" h={64} />
            <span style={{ fontFamily: FONT.film, fontWeight: 800, fontSize: 64, letterSpacing: -2, color: FILM.INK }}>Bima</span>
          </div>
          <Label x={720} y={350} px={30} weight={600} color={FILM.MINT}>
            ✓ Coverage active
          </Label>
          <Words list={[{ s: "Incident", t: inc.incident }, { s: "recorded.", t: inc.incident + 0.3 }]} t={t} x={720} y={450} px={48} />
          <Label x={720} y={496} px={28} weight={400} color={FILM.GREY} opacity={sm(inc.incident + 0.3, inc.incident + 0.7, t)}>
            Accidental injury · Pen A
          </Label>
          <Words list={[{ s: "The", t: inc.agent - 0.2 }, { s: "agent", t: inc.agent, fill: "grad" }, { s: "prepares", t: inc.claim - 0.4 }, { s: "the", t: inc.claim - 0.25 }, { s: "claim.", t: inc.claim }]} t={t} x={720} y={600} px={44} />
        </AbsoluteFill>
      ) : null}
      {listA > 0 ? (
        <AbsoluteFill style={{ opacity: listA }}>
          <Words list={[{ s: "One", t: ch.checklist - 0.2 }, { s: "checklist.", t: ch.checklist, fill: "grad" }]} t={t} x={640} y={112} px={56} glow />
          <Row y={160} t={t} at={ch.passport} label="Passport identity" sub="Muzzle re-scan: Match" state="ok" />
          <Row y={255} t={t} at={ch.observations} label="Camera observations" sub="CAM-01 · Pen A clip" state="ok" />
          <Row y={350} t={t} at={ch.policy} label="Policy details" sub="Covers accidental injury" state="ok" />
          <Row y={445} t={t} at={ch.evidence} label="Incident facts" sub="Recorded by A. Pratama" state="ok" />
          <Row y={540} t={t} at={mi.missing} label={vetOk ? "Vet assessment" : "Vet assessment missing"} sub={vetOk ? "Added by dr. R. Lestari" : t > mi.flagged ? "Submission blocked until added" : "Flagged before submission"} state={vetOk ? "ok" : "missing"} />
        </AbsoluteFill>
      ) : null}
      {subA > 0 ? (
        <AbsoluteFill style={{ opacity: subA }}>
          <Words list={[{ s: "Facts", t: su.facts }, { s: "checked.", t: su.facts + 0.3 }]} t={t} x={80} y={170} px={56} />
          <StampBig x={80} y={200} t={t} at={su.approves} text="APPROVED · 17:31 · W.S." />
          <svg width={1280} height={720} style={{ position: "absolute", inset: 0 }}>
            <line x1={x0} y1={380} x2={lerp(x0, x1, arrow)} y2={380} stroke="rgba(255,255,255,0.7)" strokeWidth={1.4} />
            {arrow > 0.98 ? <path d={`M${x1 + 10},372 L${x1},380 L${x1 + 10},388`} fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth={1.4} /> : null}
          </svg>
          <Label x={80} y={392} px={36} weight={700} opacity={sm(su.insurer - 0.1, su.insurer + 0.3, t)}>
            Sandbox Mutual
          </Label>
          <Label x={80} y={432} px={28} weight={400} color={FILM.GREY} opacity={sm(su.insurer, su.insurer + 0.4, t)}>
            simulated insurer
          </Label>
          <Words list={[{ s: "Pending", t: su.pending, fill: "#f2c94c" }, { s: "assessment.", t: su.pending + 0.35, fill: "#f2c94c" }]} t={t} x={80} y={560} px={56} />
          <Label x={82} y={610} px={28} weight={400} color={FILM.GREY} opacity={sm(su.pending + 0.4, su.pending + 0.8, t)} mono>
            Receipt {RECEIPTS.claim} · no payout yet
          </Label>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

// ---------------- 03:08-03:22 Audit trail and blocks ----------------
export const AuditFront: React.FC = () => {
  const t = useT();
  const a = sm(au.trail - 0.2, au.trail + 0.3, t) * (1 - sm(bl.uncertain - 0.4, bl.uncertain - 0.1, t));
  const b = sm(bl.uncertain - 0.1, bl.uncertain + 0.3, t) * (1 - sm(B.connects.start - 0.3, B.connects.start + 0.1, t));
  const item = (y: number, at: number, k: string, v: string) => (
    <>
      <Label x={640} y={y} px={28} weight={400} color={FILM.GREY} opacity={sm(at, at + 0.35, t)}>
        {k}
      </Label>
      <Label x={640} y={y + 44} px={36} weight={700} opacity={sm(at + 0.1, at + 0.45, t)}>
        {v}
      </Label>
    </>
  );
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: a }}>
        <Words list={[{ s: "Audit", t: au.trail, fill: "grad" }, { s: "trail.", t: au.trail + 0.3, fill: "grad" }]} t={t} x={640} y={130} px={64} glow />
        {item(230, au.identity, "Who confirmed the identity", "A. Pratama · 09:14")}
        {item(350, au.approved, "Which action was approved", "Premium · W. Santoso")}
        {item(470, au.provider, "What the provider returned", `${RECEIPTS.policy} · confirmed`)}
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: b }}>
        <Label x={640} y={190} px={28} weight={400} color={FILM.GREY} opacity={sm(bl.uncertain, bl.uncertain + 0.3, t)}>
          Identity uncertain
        </Label>
        <Label x={640} y={238} px={36} weight={700} mono color="#ff6b5e" opacity={sm(bl.uncertain + 0.1, bl.uncertain + 0.4, t)}>
          IDENTITY_UNCONFIRMED
        </Label>
        <Label x={640} y={320} px={28} weight={400} color={FILM.GREY} opacity={sm(bl.missing, bl.missing + 0.3, t)}>
          Approval missing
        </Label>
        <Label x={640} y={368} px={36} weight={700} mono color="#ff6b5e" opacity={sm(bl.missing + 0.1, bl.missing + 0.4, t)}>
          APPROVAL_REQUIRED
        </Label>
        <Words list={[{ s: "Blocked.", t: bl.blocks, fill: FILM.RED }]} t={t} x={636} y={510} px={88} />
        <StampBig x={640} y={545} t={t} at={bl.blocks + 0.3} text="NOT EXECUTED" color="#ff6b5e" />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------------- 03:22-03:31 Close ----------------
export const WIPE0 = B.tagline.start - 0.35,
  WIPE1 = B.tagline.start + 0.3;
export const CloseBack: React.FC = () => {
  const t = useT();
  const a = sm(B.connects.start - 0.4, B.connects.start + 0.4, t);
  const bx = lerp(-260, 1280 + 260, io(sm(WIPE0, WIPE1, t)));
  return (
    <AbsoluteFill style={{ opacity: a, clipPath: t > WIPE0 ? `inset(0 0 0 ${Math.max(0, bx)}px)` : undefined }}>
      <Footage name="Sari, closing" segments={[{ clip: "hp", start: B.connects.start - 0.4, end: WIPE1 + 0.1, from: 5.2, rate: 0.35 }]} frame={{ zoom: lerp(1.05, 1.15, sm(B.connects.start, WIPE1, t)), fx: 0.4, fy: 0.55 }} filter={GRADE.film} />
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(3,3,4,0.15) 0%, rgba(3,3,4,0.35) 45%, rgba(3,3,4,0.85) 66%, rgba(3,3,4,0.92) 100%)" }} />
    </AbsoluteFill>
  );
};

export const CloseFront: React.FC = () => {
  const t = useT();
  const a = sm(cn.identity - 0.2, cn.identity + 0.2, t) * (1 - sm(WIPE0, WIPE0 + 0.3, t));
  const white = t > WIPE0;
  const cardA = sm(WIPE1 - 0.1, WIPE1 + 0.5, t);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: a }}>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 320, background: "linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,0.6))" }} />
        <Words list={[{ s: "Animal", t: cn.identity - 0.3 }, { s: "identity", t: cn.identity }]} t={t} x={80} y={540} px={60} />
        <Words list={[{ s: "+", t: cn.protection - 0.4, fill: FILM.GREY }, { s: "financial", t: cn.protection, fill: "grad" }, { s: "protection.", t: cn.protection + 0.4, fill: "grad" }]} t={t} x={80} y={620} px={60} glow />
      </AbsoluteFill>
      {white ? (
        <AbsoluteFill>
          <div style={{ position: "absolute", left: 200, top: 290, width: 380, height: 214, borderRadius: 18, overflow: "hidden", opacity: cardA, boxShadow: "0 30px 60px rgba(0,0,0,0.22), 0 0 0 1px rgba(0,0,0,0.08)" }}>
            <Footage name="Sari, card" segments={[{ clip: "hp", start: WIPE1 - 0.1, end: B.tagline.end + 1.2, from: 5.6, rate: 0.3 }]} frame={{ zoom: 1.1, fx: 0.45, fy: 0.55 }} filter="contrast(1.05) saturate(1.0)" />
          </div>
          <Label x={390} y={548} px={28} weight={600} color="#6e6e73" align="center" opacity={cardA}>
            Sari · 001 · covered
          </Label>
          <Words list={[{ s: "Know", t: tg.know, fill: "#1d1d1f" }, { s: "every", t: tg.every1, fill: "#1d1d1f" }, { s: "animal.", t: tg.animal, fill: "#1d1d1f" }]} t={t} x={640} y={112} px={64} align="center" />
          <Words
            list={[{ s: "Protect", t: tg.protect, fill: "grad" }, { s: "every", t: tg.every2, fill: "grad" }, { s: "asset.", t: tg.asset, fill: "grad" }]}
            t={t}
            x={640}
            y={192}
            px={64}
            align="center"
            stops={["#7c4dff", "#d946ef", "#ff7a2f"]}
          />
          <Label x={640} y={680} px={28} weight={600} color="#6e6e73" align="center" opacity={sm(tg.asset + 0.4, tg.asset + 0.9, t)}>
            VEYRA · mobile app for cattle farms
          </Label>
        </AbsoluteFill>
      ) : null}
      <Sweep t={t} s0={WIPE0} s1={WIPE1} />
    </AbsoluteFill>
  );
};
