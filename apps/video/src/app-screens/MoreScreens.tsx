import React from "react";
import { ArrowUp, CircleCheck, CircleX, FileCheck2, Hourglass, ScanLine, Search, Stamp as StampIcon, TriangleAlert } from "lucide-react";
import { APP } from "../theme";
import { CctvView } from "../components/Cctv";
import { Segment, Still } from "../components/Footage";
import { Tap } from "../components/Phone";
import { clamp, io } from "../lib/h";
import { BIMA, MANAGER, OPERATOR, RECEIPTS, SARI, VET } from "./data";
import { Btn, EarTag, EvidenceFrame, Pill, Prov, Rule, Shell, Stamp, T, appear, mono, rise, typed } from "./ui";

// ---------------- Monitor ----------------
export const MonitorScreen: React.FC<{ t: number; segments: Segment[]; t0: number }> = ({ t, segments, t0 }) => (
  <Shell time="17:12" tab="monitor" badge={0} title={<span style={{ fontWeight: 700, fontSize: 20 }}>Monitor</span>}>
    <div style={{ padding: "14px 16px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 700, fontSize: T.title }}>CAM-01 · Pen A</span>
        <Prov kind="prototype" />
      </div>
      <div style={{ marginTop: 10 }}>
        <EvidenceFrame w={358} h={201}>
          <CctvView t={t} segments={segments} detectAt={-1} assocAt={-1} zoneAt={-1} hud={false} ui={0.45} highlightRed={-1} name="Monitor clip" />
        </EvidenceFrame>
      </div>
      <div style={{ ...mono, fontSize: 13.5, color: APP.muted, marginTop: 6 }}>Recorded replay · 17:02–17:09 · scan zone calibrated</div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10 }}>
        <EarTag num={SARI.tag} h={36} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 16.5 }}>Sari · track 11</div>
          <div style={{ fontSize: 14, color: APP.muted }}>Identified in scan zone · 31 points</div>
        </div>
      </div>
      {/* movement trend */}
      <div style={{ marginTop: 12, ...rise(t, t0 + 0.2) }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>Movement · last 7 windows</div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 60, borderBottom: `2px solid ${APP.ink}` }}>
          {[0.82, 0.9, 0.78, 0.86, 0.8, 0.74, 0.3].map((v, i) => (
            <div key={i} style={{ flex: 1, height: `${v * 100}%`, background: i === 6 ? APP.uncertain : APP.lineStrong, borderRadius: "3px 3px 0 0" }} />
          ))}
        </div>
      </div>
      {/* alert */}
      <div style={{ marginTop: 12, padding: 12, borderRadius: 14, border: `2px solid ${APP.uncertain}`, background: APP.uncertainSoft, ...rise(t, t0 + 0.4) }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 700, fontSize: 17.5, color: APP.uncertainInk }}>
          <TriangleAlert size={20} strokeWidth={2.25} /> Unusual reduced movement
        </div>
        <div style={{ ...mono, fontSize: 14, color: APP.ink, marginTop: 4 }}>17:02–17:09 vs earlier replay</div>
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <Pill tone="awaiting" label="Review required" size={0.85} />
          <Pill tone="neutral" label="Requires inspection — Not a diagnosis" size={0.85} />
        </div>
      </div>
    </div>
  </Shell>
);

// ---------------- Ask ----------------
export const AskScreen: React.FC<{ t: number; typeAt: number; sendAt: number; answerAt: number }> = ({ t, typeAt, sendAt, answerAt }) => {
  const q = "Where was Sari last seen?";
  const text = t < sendAt ? typed(q, t, typeAt, q.length / Math.max(0.5, sendAt - typeAt - 0.1)) : "";
  return (
    <Shell time="17:12" tab="more" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Ask</span>}>
      <div style={{ padding: "14px 16px" }}>
        <div style={{ fontWeight: 700, fontSize: T.h1 }}>Ask the herd</div>
        <div style={{ fontSize: 15.5, color: APP.muted, marginTop: 2 }}>Answers come from recorded observations.</div>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <div style={{ flex: 1, height: 48, borderRadius: 10, border: `2px solid ${APP.ink}`, display: "flex", alignItems: "center", gap: 8, padding: "0 12px", fontSize: 17 }}>
            <Search size={18} strokeWidth={2.25} />
            {t < sendAt ? text || <span style={{ color: APP.muted }}>Ask about an animal…</span> : <span style={{ color: APP.muted }}>Ask about an animal…</span>}
          </div>
          <div style={{ width: 48, height: 48, borderRadius: 10, background: APP.ink, display: "grid", placeItems: "center" }}>
            <ArrowUp size={22} color={APP.tag} strokeWidth={2.5} />
          </div>
        </div>
        {t >= sendAt ? (
          <div style={{ marginTop: 14, ...rise(t, sendAt) }}>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <div style={{ background: APP.ink, color: "#fff", borderRadius: "16px 16px 4px 16px", padding: "10px 14px", fontSize: 17 }}>{q}</div>
            </div>
          </div>
        ) : null}
        {t >= sendAt && t < answerAt ? <div style={{ marginTop: 14, color: APP.muted, fontSize: 16 }}>Looking through the records…</div> : null}
        {t >= answerAt ? (
          <div style={{ marginTop: 14, padding: 14, borderRadius: 14, border: `2px solid ${APP.ink}`, ...rise(t, answerAt) }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <EarTag num={SARI.tag} h={36} />
              <span style={{ fontWeight: 700, fontSize: 18 }}>Sari · {SARI.id}</span>
            </div>
            <div style={{ marginTop: 10, fontSize: 15, color: APP.muted }}>Last seen</div>
            <div style={{ ...mono, fontSize: 28, fontWeight: 700 }}>17:09 today</div>
            <div style={{ ...mono, fontSize: 16, fontWeight: 700, marginTop: 2 }}>CAM-01 · Pen A · feed line</div>
            <div style={{ marginTop: 10 }}>
              <EvidenceFrame w={326} h={150} caption="Track 11 · 17:09:18">
                <Still src="footage/cctv_frame_late.jpg" frame={{ zoom: 2.1, fx: 0.55, fy: 0.62 }} />
              </EvidenceFrame>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
              <span style={{ fontSize: 14.5, color: APP.muted, flex: 1 }}>From recorded observations, not a live location.</span>
              <Prov kind="prototype" />
            </div>
          </div>
        ) : null}
      </div>
    </Shell>
  );
};

// ---------------- Bima: incident ----------------
export const IncidentScreen: React.FC<{ t: number; t0: number; savedAt: number }> = ({ t, t0, savedAt }) => (
  <Shell time="17:24" tab="more" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Record incident</span>}>
    <div style={{ padding: "14px 16px" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <EarTag num={BIMA.tag} h={44} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 21 }}>{BIMA.name}</div>
          <div style={{ ...mono, fontSize: 14.5, color: APP.muted }}>{BIMA.id}</div>
        </div>
        <span style={{ flex: 1 }} />
        <Pill tone="ok" label="Covered" size={0.85} />
      </div>
      {[
        ["Kind", "Accidental injury"],
        ["What happened", "Left hind lameness found at the morning check."],
        ["When", "20 Oct 2026 · 07:40"],
        ["Found by", OPERATOR.name],
        ["Estimated loss", "600.00 USD · farm's own estimate"],
      ].map(([k, v], i) => (
        <div key={k} style={{ marginTop: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: APP.muted }}>{k}</div>
          <div style={{ minHeight: 44, border: `2px solid ${APP.lineStrong}`, borderRadius: 10, padding: "9px 12px", fontSize: 16.5, boxSizing: "border-box", ...(k === "When" || k === "Estimated loss" ? mono : {}) }}>
            {typed(v, t, t0 + i * 0.08, 110)}
          </div>
        </div>
      ))}
      <div style={{ marginTop: 14 }}>
        {t >= savedAt ? <Stamp kind="posted" text={`Incident recorded · 17:24 · ${OPERATOR.initials}`} press={t - savedAt} /> : <Btn label="Save incident" full pressed={t > savedAt - 0.12} />}
      </div>
      <div style={{ fontSize: 14, color: APP.muted, marginTop: 8 }}>Farmer-reported. Not a vet finding.</div>
    </div>
    <Tap t={t} at={savedAt} x={195} y={106 + 560} />
  </Shell>
);

// ---------------- Bima: claim ----------------
export type ClaimCues = {
  passport: number;
  identity: number;
  observations: number;
  policy: number;
  evidence: number;
  missing: number;
  flagged: number;
  vetAdded: number;
  declaration: number;
  approve: number;
  send: number;
  pending: number;
};

type ItemState = "ok" | "missing" | "pending" | "hidden";
const Item: React.FC<{ label: string; sub: string; state: ItemState; t: number; at: number }> = ({ label, sub, state, t, at }) =>
  state === "hidden" ? null : (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "8px 0", borderBottom: `1px solid ${APP.line}`, ...rise(t, at, 0.3, 8) }}>
      {state === "ok" ? (
        <CircleCheck size={21} color={APP.ok} strokeWidth={2.25} style={{ flex: "none", marginTop: 1 }} />
      ) : state === "missing" ? (
        <TriangleAlert size={21} color={APP.uncertain} strokeWidth={2.25} style={{ flex: "none", marginTop: 1 }} />
      ) : (
        <Hourglass size={21} color={APP.awaitInk} strokeWidth={2.25} style={{ flex: "none", marginTop: 1 }} />
      )}
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 16.5, color: state === "missing" ? APP.uncertainInk : APP.ink }}>{label}</div>
        <div style={{ fontSize: 14, color: APP.muted, ...mono }}>{sub}</div>
      </div>
    </div>
  );

export const ClaimScreen: React.FC<{ t: number; c: ClaimCues }> = ({ t, c }) => {
  const scroll = t < c.declaration ? 0 : 300 * io(clamp((t - c.declaration) / 0.6));
  const vet: ItemState = t < c.missing ? "hidden" : t < c.vetAdded ? "missing" : "ok";
  const blocked = t >= c.flagged && t < c.vetAdded;
  const submitted = t >= c.send;
  return (
    <Shell time="17:31" tab="more" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Claim · draft</span>}>
      <div style={{ translate: `0 ${-scroll}px` }}>
        <div style={{ padding: "14px 16px 6px", display: "flex", gap: 10, alignItems: "center" }}>
          <EarTag num={BIMA.tag} h={40} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 19 }}>Bima · accidental injury</div>
            <div style={{ fontSize: 14, color: APP.muted }}>Basic Mortality & Accident · SBX-POL-0311</div>
          </div>
        </div>
        <div style={{ padding: "0 16px" }}>
          <div style={{ fontWeight: 700, fontSize: 18, padding: "8px 0 2px" }}>Evidence checklist</div>
          <Item label="Passport identity reference" sub="animal-demo-002 · muzzle on file" state="ok" t={t} at={c.passport} />
          {/* claim-time muzzle identity check */}
          {t >= c.identity ? (
            <div style={{ margin: "8px 0", padding: 10, borderRadius: 12, border: `2px solid ${APP.ink}`, ...rise(t, c.identity) }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <Pill tone="ok" label="Match" size={0.85} />
                <span style={{ fontWeight: 700, fontSize: 15.5 }}>Verify identity</span>
                <span style={{ flex: 1 }} />
                <Prov kind="prototype" />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <EvidenceFrame w={160} h={74} caption="Enrolled muzzle">
                  <Still src="footage/muzzle_closeup.jpg" frame={{ zoom: 1.1, fx: 0.5, fy: 0.45 }} />
                </EvidenceFrame>
                <EvidenceFrame w={160} h={74} caption="Claim scan">
                  <Still src="footage/muzzle_closeup.jpg" frame={{ zoom: 1.35, fx: 0.46, fy: 0.5 }} filter="brightness(0.92) contrast(1.05)" />
                </EvidenceFrame>
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: APP.ok, marginTop: 6 }}>Identity verified: the checklist item is on file.</div>
            </div>
          ) : null}
          <Item label="Camera observations" sub="CAM-01 · Pen A · 07:12–07:38 clip" state="ok" t={t} at={c.observations} />
          <Item label="Active policy" sub="covers accidental injury · sample-v1" state="ok" t={t} at={c.policy} />
          <Item label="Incident facts" sub="recorded 17:24 · A. Pratama" state="ok" t={t} at={c.evidence} />
          <Item label={vet === "missing" ? "Vet assessment · missing" : "Vet assessment"} sub={vet === "missing" ? `Requested from ${VET}` : `Added by ${VET} · 17:30`} state={vet} t={t} at={c.missing} />
          <Item label="Farmer declaration" sub={t >= c.declaration ? `Confirmed by ${MANAGER.name}` : "Waiting for the manager"} state={t >= c.declaration ? "ok" : "pending"} t={t} at={c.evidence + 0.2} />
        </div>
        <div style={{ padding: "12px 16px" }}>
          {blocked ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", padding: 10, borderRadius: 10, background: APP.uncertainSoft, color: APP.uncertainInk, fontWeight: 700, fontSize: 15.5, marginBottom: 10 }}>
              <CircleX size={18} strokeWidth={2.25} /> Submission blocked: 1 item missing
            </div>
          ) : null}
          {submitted ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Stamp kind="approved" text={`Approved · 20 Oct 17:31 · ${MANAGER.initials}`} />
              <div style={{ padding: 12, borderRadius: 14, border: `2px solid ${APP.tagEdge}`, background: APP.tagSoft }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 700, fontSize: 18, color: APP.awaitInk }}>
                  <Hourglass size={20} strokeWidth={2.25} /> {t >= c.pending ? "Submitted — Pending assessment" : "Sending to Sandbox Mutual…"}
                </div>
                <div style={{ ...mono, fontSize: 14, marginTop: 4 }}>Receipt {RECEIPTS.claim} · simulated insurer</div>
                <div style={{ fontSize: 14, color: APP.muted, marginTop: 4 }}>No payout yet. The insurer assesses the claim.</div>
              </div>
              <Btn v="secondary" label="Track claim status" icon={FileCheck2} full />
            </div>
          ) : (
            <Btn v={t < c.vetAdded ? "disabled" : "primary"} label={t >= c.declaration ? "Approve and stamp" : "Submit claim"} icon={StampIcon} h={52} full pressed={t > c.approve - 0.12 && t < c.approve + 0.1} />
          )}
        </div>
      </div>
      <Tap t={t} at={c.approve} x={195} y={106 + 760 - 300} />
    </Shell>
  );
};

// ---------------- Audit ----------------
type AuditLine = { n: string; time: string; title: string; who: string; stamp: { kind: "confirmed" | "approved" | "posted" | "failed" | "unknown"; text: string }; at: number; blocked?: boolean };
export const AuditScreen: React.FC<{ t: number; lines: AuditLine[]; scrollAt: number }> = ({ t, lines, scrollAt }) => {
  const scroll = 330 * io(clamp((t - scrollAt) / 0.8));
  return (
    <Shell time="17:42" tab="more" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Audit</span>}>
      <div style={{ translate: `0 ${-scroll}px` }}>
        <div style={{ padding: "14px 16px 8px" }}>
          <div style={{ fontWeight: 700, fontSize: T.h1 }}>Audit trail</div>
          <div style={{ fontSize: 15, color: APP.muted }}>Who did what, and what the provider returned.</div>
        </div>
        <Rule w={3} color={APP.ink} />
        {lines.map((l) =>
          t >= l.at - 0.05 ? (
            <div key={l.n} style={{ display: "grid", gridTemplateColumns: "54px 1fr", gap: 8, padding: "10px 14px", borderBottom: `1px solid ${APP.line}`, background: l.blocked ? APP.dangerSoft : APP.bg, ...rise(t, l.at, 0.3, 8) }}>
              <div style={{ ...mono }}>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{l.n}</div>
                <div style={{ fontSize: 13, color: APP.muted }}>{l.time}</div>
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16, color: l.blocked ? APP.danger : APP.ink }}>{l.title}</div>
                <div style={{ fontSize: 14, color: APP.muted }}>{l.who}</div>
                <div style={{ marginTop: 6 }}>
                  <Stamp kind={l.stamp.kind} text={l.stamp.text} press={t - l.at} />
                </div>
              </div>
            </div>
          ) : null,
        )}
      </div>
    </Shell>
  );
};

export { ScanLine, appear };
