import React from "react";
import { B } from "./beats";
import { PhoneScreen } from "./components/PhoneScreen";
import { HerdScreen, LaunchScreen } from "./app-screens/HerdScreen";
import { ReviewScreen, ScanScreen } from "./app-screens/EnrollScreens";
import { PassportScreen } from "./app-screens/PassportScreen";
import { AgentScreen, Msg, PlanRows, Reason, say } from "./app-screens/AgentScreen";
import { ApplicationScreen } from "./app-screens/ApplicationScreen";
import { AskScreen, AuditScreen, ClaimScreen, IncidentScreen, MonitorScreen } from "./app-screens/MoreScreens";
import { Btn } from "./app-screens/ui";
import { BIMA, INSURED_VALUE, MANAGER, OPERATOR, PREMIUM, RECEIPTS, SARI, usd } from "./app-screens/data";
import { MONITOR_PHONE_SEGMENTS, SCAN_SEGMENTS } from "./footage-plan";

// Which app screen the hero phone shows at film time t. Each state names the capture it maps to
// (public/app/captures.json: herd, enroll-scan, scan-quality, passport, agent-insurance, monitor, ask,
// agent-claim, claim, claim-identity, audit) and the key moment it starts from. Without that capture,
// the state renders its Ear Tag recreation.
type State = { from: number; capture?: string; moment?: string; render: (t: number) => React.ReactNode };

const m = B.meet.cue,
  h = B.herd.cue,
  c = B.capture.cue,
  e = B.extract.cue,
  p = B.passport.cue,

  v = B.valuation.cue,
  gp = B.gap.cue,

  tr = B.tradeoffs.cue,
  pr = B.prepare.cue,
  ar = B.approvalRule.cue,
  ap = B.approve.cue,
  sb = B.sandbox.cue,
  ac = B.activation.cue,
  nd = B.notDiagnosis.cue,
  ask = B.ask.cue,
  inc = B.incident.cue,
  ch = B.checklist.cue,
  mi = B.missing.cue,
  su = B.submit.cue,
  au = B.audit.cue,
  bl = B.blocks.cue,
  cn = B.connects.cue;

// ---- the insurance agent conversation (uninsured Sari) ----
const FIND_TAP = gp.next + 0.45;
const AGENT_OPEN = gp.next + 0.8;
const CHOOSE_TAP = tr.informed;
export const INSURANCE_MSGS: Msg[] = [
  {
    at: gp.assistant,
    from: "agent",
    h: 92,
    body: (t) => <span>{say("Sari (001) has no active insurance. I can find cover and prepare everything for your approval.", t, gp.assistant)}</span>,
  },
  {
    at: gp.compares,
    from: "agent",
    h: 300,
    body: (t) => (
      <div>
        <span>{say("I found 3 plans for this cow based on its confirmed details.", t, gp.compares)}</span>
        <PlanRows t={t} t0={gp.three} />
      </div>
    ),
  },
  {
    at: tr.instead - 0.2,
    from: "agent",
    h: 72,
    body: (t) => <span>{say("One question first: do you need theft cover for Sari now?", t, tr.instead - 0.2)}</span>,
  },
  { at: tr.cheapest + 0.5, from: "user", h: 44, body: () => <span>Not yet. No ownership document on file.</span> },
  {
    at: tr.explains,
    from: "agent",
    h: 250,
    body: (t) => (
      <div>
        <div style={{ fontWeight: 700 }}>Recommended: Basic Mortality & Accident</div>
        <Reason>Eligible today: identity, age and valuation are confirmed.</Reason>
        <Reason>{`${usd(PREMIUM)} USD a year on ${usd(INSURED_VALUE)} USD insured.`}</Reason>
        <Reason ok={false}>Tradeoff: no theft cover. Add an ownership document to qualify for Mortality + Theft.</Reason>
        <div style={{ marginTop: 10, opacity: t > tr.tradeoffs ? 1 : 0.4 }}>
          <Btn label="Choose this plan" full h={44} pressed={t > CHOOSE_TAP - 0.12 && t < CHOOSE_TAP + 0.12} />
        </div>
      </div>
    ),
  },
  { at: tr.choice, from: "user", h: 44, body: () => <span>Choose Basic Mortality & Accident.</span> },
  {
    at: pr.selects,
    from: "agent",
    h: 96,
    body: (t) => (
      <div>
        <span>{say("I'll prepare the application and a separate premium payment. Nothing is sent until you stamp it.", t, pr.selects)}</span>
        <div style={{ marginTop: 8 }}>
          <Btn label="Prepare application" full h={44} pressed={t > pr.agent && t < pr.agent + 0.2} />
        </div>
      </div>
    ),
  },
];

// ---- the claim conversation (insured Bima) ----
const CLAIM_MSGS: Msg[] = [
  { at: inc.agent, from: "user", h: 44, body: () => <span>Help me file an insurance claim.</span> },
  {
    at: inc.claim - 0.3,
    from: "agent",
    h: 120,
    body: (t) => <span>{say("Bima's Basic Mortality & Accident policy is active and covers accidental injury. I'll gather the evidence into one checklist.", t, inc.claim - 0.3)}</span>,
  },
];

const AUDIT_LINES = [
  { n: "01", time: "09:14", title: "Identity confirmed · Sari 001", who: `Muzzle reference · ${OPERATOR.name}`, stamp: { kind: "confirmed" as const, text: `Confirmed · ${OPERATOR.initials}` }, at: au.identity },
  { n: "02", time: "09:31", title: "Approved · Policy application", who: `Prepared by the VEYRA AI agent · ${MANAGER.name}`, stamp: { kind: "approved" as const, text: `Approved · ${MANAGER.initials}` }, at: au.approved },
  { n: "03", time: "09:31", title: `Approved · Premium ${usd(PREMIUM)} USD`, who: `Sandbox wallet · ${MANAGER.name}`, stamp: { kind: "approved" as const, text: `Approved · ${MANAGER.initials}` }, at: au.approved + 0.3 },
  { n: "04", time: "09:33", title: "Provider receipt · coverage confirmed", who: `Sandbox Mutual · ${RECEIPTS.policy}`, stamp: { kind: "posted" as const, text: "Posted · sandbox" }, at: au.provider },
  { n: "05", time: "17:31", title: "Claim submitted · Bima 002", who: `Sandbox Mutual · ${RECEIPTS.claim}`, stamp: { kind: "unknown" as const, text: "Assessment pending" }, at: au.provider + 0.35 },
  { n: "06", time: "17:40", title: "Blocked · claim for an unconfirmed track", who: "IDENTITY_UNCONFIRMED", stamp: { kind: "failed" as const, text: "Blocked" }, at: bl.uncertain, blocked: true },
  { n: "07", time: "17:41", title: "Blocked · payment without approval", who: "APPROVAL_REQUIRED", stamp: { kind: "failed" as const, text: "Blocked" }, at: bl.missing, blocked: true },
];

export const STATES: State[] = [
  { from: 0, render: (t) => <LaunchScreen t={t} t0={m.veyra - 0.2} /> },
  { from: m.connects - 0.3, capture: "herd", moment: "herd", render: (t) => <HerdScreen t={t} t0={m.connects - 0.3} /> },
  { from: h.herd, capture: "herd", moment: "herd", render: (t) => <HerdScreen t={t} enrollTap={t > c.add - 0.2 && t < c.add + 0.15} /> },
  {
    from: c.add + 0.2,
    capture: "scan-quality",
    moment: "muzzle",
    render: (t) => (
      <ScanScreen t={t} segments={SCAN_SEGMENTS} recAt={c.add + 0.2} teethAt={c.teeth} bodyAt={c.body} qualityFrom={c.guided} qualityTo={c.nose + 0.3} capturedAt={c.nose + 0.3} />
    ),
  },
  { from: e.extracts - 0.3, capture: "enroll-scan", moment: "review", render: (t) => <ReviewScreen t={t} uploadAt={e.extracts - 0.3} framesAt={e.images} candidateAt={e.person - 0.3} confirmAt={e.confirm} /> },
  {
    from: p.confirmed,
    capture: "passport",
    moment: "passport",
    render: (t) => {
      const sc = t < v.calculates ? 0 : t < gp.next - 0.6 ? 560 : 680;
      const ease = Math.min(1, Math.max(0, (t - (t < gp.next - 0.6 ? v.calculates : gp.next - 0.6)) / 0.6));
      const prev = t < v.calculates ? 0 : t < gp.next - 0.6 ? 0 : 560;
      return <PassportScreen t={t} createdAt={p.confirmed} scroll={prev + (sc - prev) * (ease * ease * (3 - 2 * ease))} calcAt={v.weight} findTap={FIND_TAP} />;
    },
  },
  {
    from: AGENT_OPEN,
    capture: "agent-insurance",
    moment: "proactive",
    render: (t) => <AgentScreen t={t} title="Sari" tag={SARI.tag} msgs={INSURANCE_MSGS} taps={[{ at: CHOOSE_TAP, x: 220, y: 700 }]} time="09:20" />,
  },
  {
    from: pr.prepares,
    capture: "agent-insurance",
    moment: "application",
    render: (t) => (
      <ApplicationScreen
        t={t}
        c={{ fill: pr.prepares + 0.2, checklist: pr.application + 0.3, actions: pr.separate, scrollTo: ar.nothing - 0.3, stamp1: ap.approves, stamp2: ap.each, receipt: ap.response, payment: ac.payment, confirm: ac.confirms }}
      />
    ),
  },
  // monitor: the phone is off stage during the CCTV full-frame, back for the Monitor screen
  { from: nd.inspect - 0.9, capture: "monitor", moment: "alert", render: (t) => <MonitorScreen t={t} segments={MONITOR_PHONE_SEGMENTS} t0={nd.inspect - 0.9} /> },
  { from: ask.ask - 0.4, capture: "ask", moment: "query", render: (t) => <AskScreen t={t} typeAt={ask.question} sendAt={ask.seen + 0.5} answerAt={ask.answer} /> },
  { from: inc.later - 0.4, capture: "passport", moment: "bima", render: (t) => <PassportScreen t={t} animal={BIMA} coverage="bima" scroll={680} incidentTap={inc.incident - 0.2} time="17:22" /> },
  { from: inc.incident + 0.05, capture: "claim", moment: "incident", render: (t) => <IncidentScreen t={t} t0={inc.incident + 0.1} savedAt={inc.agent - 0.15} /> },
  { from: inc.agent + 0.1, capture: "agent-claim", moment: "request", render: (t) => <AgentScreen t={t} title="Bima" tag={BIMA.tag} msgs={CLAIM_MSGS} time="17:25" /> },
  {
    from: ch.gathers,
    capture: "claim-identity",
    moment: "checklist",
    render: (t) => (
      <ClaimScreen
        t={t}
        c={{
          passport: ch.passport,
          identity: ch.passport + 0.45,
          observations: ch.observations,
          policy: ch.policy,
          evidence: ch.evidence,
          missing: mi.missing,
          flagged: mi.flagged,
          vetAdded: mi.submission + 0.45,
          declaration: su.facts,
          approve: su.approves,
          send: su.send,
          pending: su.pending,
        }}
      />
    ),
  },
  { from: au.every - 0.2, capture: "audit", moment: "trail", render: (t) => <AuditScreen t={t} lines={AUDIT_LINES} scrollAt={bl.uncertain - 0.4} /> },
  { from: cn.veyra - 0.2, capture: "passport", moment: "covered", render: (t) => <PassportScreen t={t} coverage="active" monitoring time="17:45" /> },
];

export const ScreenRouter: React.FC<{ t: number }> = ({ t }) => {
  let i = 0;
  for (let k = 0; k < STATES.length; k++) if (t >= STATES[k].from) i = k;
  const s = STATES[i];
  const until = STATES[i + 1]?.from;
  return (
    <PhoneScreen capture={s.capture} moment={s.moment} since={s.from} until={until}>
      {s.render(t)}
    </PhoneScreen>
  );
};

export { sb };
