import React from "react";
import { AbsoluteFill } from "remotion";
import { B } from "../beats";
import { Label, Words } from "../components/Type";
import { eo, sm } from "../lib/h";
import { useT } from "../lib/time";
import { FILM, FONT, gradCss } from "../theme";
import { PLANS, Plan } from "../app-screens/data";

// 01:28-01:51 The insurance gap first, then the in-app VEYRA AI agent compares three sample plans and explains
// the tradeoffs; the manager makes the choice.
const gp = B.gap.cue;
const pl = B.plans.cue;
const tr = B.tradeoffs.cue;

const ROWS: Record<Plan["id"], { covers: string; excludes: string; gap: string }> = {
  "basic-mortality": { covers: "Covers death and injury", excludes: "Excludes pre-existing illness", gap: "Gap: no theft" },
  "mortality-theft": { covers: "Adds theft cover", excludes: "Excludes unreported theft", gap: "Gap: ownership doc" },
  "dairy-health-plus": { covers: "Covers illness", excludes: "Dairy breeds only", gap: "Sari is beef cattle" },
};
const TONE = { eligible: "#7cf0b8", review: "#ffb26b", ineligible: "#ff6b5e" } as const;
const MARK = { eligible: "✓", review: "!", ineligible: "✕" } as const;

const PlanCard: React.FC<{ p: Plan; i: number; t: number }> = ({ p, i, t }) => {
  const x = 492 + i * 250;
  const a = eo((t - (gp.three + i * 0.18)) / 0.5);
  const row = (at: number) => ({ opacity: eo((t - at) / 0.35), translate: `0 ${(1 - eo((t - at) / 0.35)) * 8}px` });
  const r = ROWS[p.id];
  const rec = p.status === "eligible";
  const recP = sm(tr.explains, tr.explains + 0.5, t);
  const dim = p.status === "ineligible" ? 1 - 0.55 * recP : 1;
  const chosen = rec && t >= tr.choice;
  const line: React.CSSProperties = { fontFamily: FONT.film, fontSize: 28, lineHeight: 1.12, letterSpacing: -0.5, marginTop: 14 };
  return (
    <div style={{ position: "absolute", left: x, top: 140 + (1 - a) * 40, width: 236, height: 500, opacity: a * dim }}>
      {rec && recP > 0 ? (
        <div style={{ position: "absolute", inset: -3, borderRadius: 21, background: gradCss(FILM.GV, 135), opacity: recP, filter: `drop-shadow(0 0 ${14 * recP}px rgba(220,110,255,0.6))` }} />
      ) : null}
      <div style={{ position: "absolute", inset: 0, borderRadius: 18, background: "rgba(22,23,30,0.94)", boxShadow: "0 0 0 1px rgba(255,255,255,0.16), 0 24px 50px rgba(0,0,0,0.5)", padding: 16, boxSizing: "border-box", color: FILM.INK }}>
        <div style={{ fontFamily: FONT.film, fontWeight: 700, fontSize: 28, lineHeight: 1.08, letterSpacing: -0.6, minHeight: 62 }}>{p.name}</div>
        <div style={{ ...row(pl.eligibility), marginTop: 12, display: "inline-flex", alignItems: "center", gap: 8, height: 40, padding: "0 12px", borderRadius: 20, border: `2px solid ${TONE[p.status]}`, color: TONE[p.status], fontFamily: FONT.film, fontWeight: 700, fontSize: 28 }}>
          <span>{MARK[p.status]}</span>
          {p.status === "review" ? "Review" : p.status === "ineligible" ? "Ineligible" : p.statusLabel}
        </div>
        <div style={{ ...row(pl.premiums), marginTop: 14, fontFamily: FONT.film, fontWeight: 800, fontSize: 34, letterSpacing: -1 }}>
          {p.premium === "—" ? "—" : p.premium.split(" ")[0]}
          <span style={{ fontWeight: 400, fontSize: 28, color: FILM.GREY }}>{p.premium === "—" ? "" : " USD/yr"}</span>
        </div>
        <div style={{ ...row(pl.coverage), ...line }}>{r.covers}</div>
        <div style={{ ...row(pl.exclusions), ...line, color: FILM.GREY }}>{r.excludes}</div>
        <div style={{ ...row(pl.gaps), ...line, color: "#ffb26b", fontWeight: 600 }}>{r.gap}</div>
      </div>
      {rec ? (
        <div style={{ position: "absolute", left: 0, right: 0, top: 512, textAlign: "center", fontFamily: FONT.film, fontWeight: 700, fontSize: 28, color: chosen ? FILM.MINT : FILM.INK, opacity: recP }}>
          {chosen ? "✓ Chosen" : "Recommended"}
        </div>
      ) : null}
    </div>
  );
};

export const InsuranceFront: React.FC = () => {
  const t = useT();
  const gapA = sm(gp.next - 0.1, gp.next + 0.3, t) * (1 - sm(gp.three - 0.5, gp.three - 0.1, t));
  const cardsA = 1 - sm(B.prepare.start - 0.3, B.prepare.start + 0.2, t);
  const headA = sm(tr.cheapest - 0.1, tr.cheapest + 0.3, t) * (1 - sm(tr.tradeoffs - 0.3, tr.tradeoffs, t));
  const head2 = sm(tr.tradeoffs, tr.tradeoffs + 0.3, t);
  return (
    <AbsoluteFill>
      {gapA > 0 ? (
        <AbsoluteFill style={{ opacity: gapA }}>
          <Words list={[{ s: "No", t: gp.next, fill: "#ff6b5e" }, { s: "active", t: gp.next + 0.12, fill: "#ff6b5e" }]} t={t} x={80} y={300} px={64} />
          <Words list={[{ s: "insurance.", t: gp.next + 0.24, fill: "#ff6b5e" }]} t={t} x={80} y={375} px={64} />
          <Label x={82} y={430} px={30} weight={400} color={FILM.GREY} opacity={sm(gp.next + 0.3, gp.next + 0.7, t)}>
            Sari · 001 · Not insured
          </Label>
          <Words list={[{ s: "VEYRA", t: gp.assistant }, { s: "AI", t: gp.assistant + 0.12, fill: "grad" }, { s: "agent", t: gp.assistant + 0.24, fill: "grad" }]} t={t} x={860} y={300} px={48} />
          <Label x={862} y={350} px={28} weight={400} color={FILM.GREY} opacity={sm(gp.compares, gp.compares + 0.4, t)}>
            Speaks first, in the app
          </Label>
          <Label x={862} y={392} px={28} weight={400} color={FILM.GREY} opacity={sm(gp.compares + 0.3, gp.compares + 0.7, t)}>
            Checks eligibility
          </Label>
        </AbsoluteFill>
      ) : null}
      {t > gp.three - 0.2 && cardsA > 0 ? (
        <AbsoluteFill style={{ opacity: cardsA }}>
          {PLANS.map((p, i) => (
            <PlanCard key={p.id} p={p} i={i} t={t} />
          ))}
          <Label x={492} y={86} px={28} weight={600} color={FILM.GREY} opacity={sm(gp.three, gp.three + 0.4, t) * (1 - headA) * (1 - head2)}>
            3 sample plans · fictional terms
          </Label>
          <Words list={[{ s: "Not", t: tr.cheapest - 0.05 }, { s: "just", t: tr.cheapest + 0.1 }, { s: "the", t: tr.cheapest + 0.22 }, { s: "cheapest.", t: tr.cheapest + 0.34 }]} t={t} x={492} y={92} px={48} alpha={headA} />
          <Words list={[{ s: "Tradeoffs,", t: tr.tradeoffs, fill: "grad" }, { s: "explained.", t: tr.tradeoffs + 0.3 }]} t={t} x={492} y={92} px={48} alpha={head2} />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
