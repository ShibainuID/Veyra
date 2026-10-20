import React from "react";
import { Calculator, Cctv, FileText, ShieldCheck, ShieldOff, Sparkles, Video } from "lucide-react";
import { APP } from "../theme";
import { Still } from "../components/Footage";
import { Tap } from "../components/Phone";
import { clamp } from "../lib/h";
import { Animal, BIMA, OPERATOR, PRICE_PER_KG, SARI, usd, usd0 } from "./data";
import { Btn, EarTag, EvidenceFrame, Pill, Prov, Rule, Shell, Stamp, T, appear, mono, rise } from "./ui";

export type PassportOpts = {
  t: number;
  animal?: Animal;
  /** when each section appears (absolute s); undefined = already there */
  createdAt?: number;
  scroll?: number;
  coverage?: "none" | "active" | "bima";
  /** highlight the coverage block and tap "Find insurance" at this time */
  findTap?: number;
  monitoring?: boolean;
  time?: string;
  /** time the valuation inputs fill */
  calcAt?: number;
  incidentTap?: number;
};

const Section: React.FC<{ title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; style?: React.CSSProperties }> = ({ title, icon, right, children, style }) => (
  <div style={{ padding: "14px 16px", ...style }}>
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 19 }}>
        {icon}
        {title}
      </span>
      {right}
    </div>
    {children}
  </div>
);

const Fact: React.FC<{ k: string; v: React.ReactNode; chip?: React.ReactNode }> = ({ k, v, chip }) => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 0", borderBottom: `1px solid ${APP.line}` }}>
    <span style={{ fontSize: 16, color: APP.muted }}>{k}</span>
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span style={{ ...mono, fontSize: 17, fontWeight: 700 }}>{v}</span>
      {chip}
    </span>
  </div>
);

/** Digital Livestock Passport. Section offsets (content px, before scroll) are exported for callout anchors. */
export const PASSPORT_Y = { header: 0, identity: 150, estimates: 300, history: 440, documents: 520, valuation: 640, coverage: 900 };

export const PassportScreen: React.FC<PassportOpts> = ({ t, animal = SARI, createdAt, scroll = 0, coverage = "none", findTap, monitoring, time = "09:15", calcAt, incidentTap }) => {
  const isSari = animal.id === SARI.id;
  const c0 = createdAt ?? -100;
  const calc = calcAt == null ? 1 : clamp((t - calcAt) / 0.6);
  const lo = animal.kg[0] * PRICE_PER_KG,
    hi = animal.kg[1] * PRICE_PER_KG;
  return (
    <Shell time={time} tab="herd" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Passport</span>}>
      <div style={{ translate: `0 ${-scroll}px` }}>
        {/* header */}
        <div style={{ padding: "16px 16px 12px", display: "flex", gap: 14, alignItems: "center", ...rise(t, c0) }}>
          <EarTag num={animal.tag} state="confirmed" h={84} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: T.h1, lineHeight: 1.1 }}>{animal.name}</div>
            <div style={{ ...mono, fontSize: 15, color: APP.muted, marginTop: 4 }}>{animal.id}</div>
            <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
              <Pill tone="ok" label="Identity confirmed" size={0.9} />
              {coverage === "none" ? <Pill tone="danger" label="Not insured" size={0.9} /> : <Pill tone="ok" label="Covered" icon={ShieldCheck} size={0.9} />}
            </div>
          </div>
        </div>
        <Rule w={2} color={APP.ink} />
        {/* identity images */}
        <Section title="Identity images" right={<Prov kind="prototype" />} style={rise(t, c0 + 0.2)}>
          <div style={{ display: "flex", gap: 8 }}>
            <EvidenceFrame w={114} h={92} caption="Muzzle">
              <Still src={isSari ? "footage/hp_muzzle.jpg" : "footage/muzzle_closeup.jpg"} frame={isSari ? { zoom: 1.5, fx: 0.38, fy: 0.42 } : { zoom: 1.1, fx: 0.5, fy: 0.45 }} />
            </EvidenceFrame>
            <EvidenceFrame w={114} h={92} caption="Body">
              <Still src={isSari ? "footage/hp_body_side.jpg" : "footage/cctv_frame_early.jpg"} frame={isSari ? { zoom: 1.25, fx: 0.45, fy: 0.5 } : { zoom: 4, fx: 0.62, fy: 0.36 }} />
            </EvidenceFrame>
            <EvidenceFrame w={114} h={92} caption={isSari ? "Teeth" : "Teeth"}>
              <Still src={isSari ? "footage/hp_muzzle.jpg" : "footage/muzzle_closeup.jpg"} frame={isSari ? { zoom: 2.4, fx: 0.38, fy: 0.95 } : { zoom: 1.8, fx: 0.5, fy: 0.95 }} />
            </EvidenceFrame>
          </div>
          <div style={{ ...mono, fontSize: 14, color: APP.muted, marginTop: 8 }}>{isSari ? `Confirmed 20 Oct 09:14 · ${OPERATOR.name}` : "Confirmed 30 Aug 08:05 · A. Pratama"}</div>
        </Section>
        <Rule />
        {/* estimates */}
        <Section title="Estimates" right={<span style={{ fontSize: 14, fontWeight: 700, color: APP.uncertainInk }}>Estimated, not guaranteed</span>} style={rise(t, c0 + 0.35)}>
          <Fact k="Age" v={isSari ? "24–30 mo" : "38–44 mo"} chip={<Prov kind="simulated" />} />
          <Fact k="Weight" v={`${animal.kg[0]}–${animal.kg[1]} kg`} chip={<Prov kind="prototype" />} />
        </Section>
        <Rule />
        {/* observation history */}
        <Section title="Observation history" icon={<Cctv size={19} strokeWidth={2.25} />} style={rise(t, c0 + 0.5)}>
          <div style={{ fontSize: 16, color: monitoring ? APP.ink : APP.muted }}>
            {monitoring ? (
              <span style={{ ...mono }}>Last seen 17:09 · Pen A · feed line</span>
            ) : isSari ? (
              "No camera observations yet"
            ) : (
              <span style={{ ...mono }}>Last seen 17:20 · Pen A · feed line</span>
            )}
          </div>
        </Section>
        <Rule />
        {/* documents */}
        <Section title="Documents" icon={<FileText size={19} strokeWidth={2.25} />} style={rise(t, c0 + 0.65)}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 16 }}>
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              <Video size={17} strokeWidth={2.25} /> Enrollment video · 00:08
            </span>
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center", color: APP.muted, border: `2px dashed ${APP.lineStrong}`, borderRadius: 8, padding: "4px 8px", alignSelf: "flex-start" }}>
              Ownership document · not on file
            </span>
          </div>
        </Section>
        <Rule w={2} color={APP.ink} />
        {/* valuation calculator */}
        <Section title="Indicative value" icon={<Calculator size={19} strokeWidth={2.25} />} right={<Prov kind="documented" />}>
          <Fact k="Confirmed weight" v={calc > 0.2 ? `${animal.kg[0]}–${animal.kg[1]} kg` : "—"} />
          <Fact k="Price per kg" v={calc > 0.6 ? `${PRICE_PER_KG.toFixed(2)} USD` : "—"} />
          <div style={{ ...mono, fontSize: 13.5, color: APP.muted, padding: "6px 0" }}>Demo reference price (fictional) · 01 Oct 2026</div>
          <div style={{ marginTop: 6, padding: 12, borderRadius: 10, border: `2px solid ${APP.ink}`, opacity: 0.25 + 0.75 * calc }}>
            <div style={{ fontSize: 15, color: APP.muted }}>Value range</div>
            <div style={{ ...mono, fontSize: 26, fontWeight: 700 }}>
              {usd0(lo)}–{usd0(hi)} USD
            </div>
            <div style={{ fontSize: 14, color: APP.uncertainInk, fontWeight: 700, marginTop: 4 }}>Estimate. Not a selling price or a payout.</div>
          </div>
        </Section>
        <Rule w={2} color={APP.ink} />
        {/* coverage */}
        <Section title="Coverage" icon={coverage === "none" ? <ShieldOff size={19} strokeWidth={2.25} /> : <ShieldCheck size={19} strokeWidth={2.25} />}>
          {coverage === "none" ? (
            <div style={{ padding: 14, borderRadius: 14, background: APP.dangerSoft, border: `2px solid ${APP.danger}` }}>
              <div style={{ fontWeight: 700, fontSize: 21, color: APP.danger }}>No active insurance</div>
              <div style={{ fontSize: 15.5, color: APP.ink, marginTop: 4 }}>Indicative exposure {usd(lo)} USD</div>
              <div style={{ marginTop: 12 }}>
                <Btn label="Find insurance" icon={Sparkles} full pressed={findTap != null && t > findTap - 0.1 && t < findTap + 0.25} />
              </div>
            </div>
          ) : (
            <div style={{ padding: 14, borderRadius: 14, background: APP.okSoft, border: `2px solid ${APP.ok}` }}>
              <div style={{ fontWeight: 700, fontSize: 20, color: APP.ok }}>Coverage active</div>
              <div style={{ fontSize: 15.5, marginTop: 4 }}>Basic Mortality & Accident · Sandbox Mutual</div>
              <div style={{ ...mono, fontSize: 14, color: APP.muted, marginTop: 4 }}>{coverage === "bima" ? "from 01 Sep 2026 · SBX-POL-0311" : "from 20 Oct 2026 · SBX-POL-0417"}</div>
              {coverage === "bima" ? (
                <div style={{ marginTop: 12 }}>
                  <Btn v="secondary" label="Record an incident" full pressed={incidentTap != null && t > incidentTap - 0.1 && t < incidentTap + 0.25} />
                </div>
              ) : null}
            </div>
          )}
        </Section>
      </div>
      {findTap != null ? <Tap t={t} at={findTap} x={195} y={(PASSPORT_Y.coverage - scroll) + 106 + 150} /> : null}
      {incidentTap != null ? <Tap t={t} at={incidentTap} x={195} y={(PASSPORT_Y.coverage - scroll) + 106 + 150} /> : null}
      {appear(t, c0) < 1 && createdAt != null ? <div style={{ position: "absolute", inset: 0, background: APP.bg, opacity: 1 - appear(t, c0, 0.5) }} /> : null}
    </Shell>
  );
};

export { BIMA, Stamp };
