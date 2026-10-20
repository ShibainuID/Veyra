import React from "react";
import { CircleCheck, CircleMinus, Hourglass, Stamp as StampIcon, X } from "lucide-react";
import { APP } from "../theme";
import { clamp, io } from "../lib/h";
import { Tap } from "../components/Phone";
import { INSURED_VALUE, MANAGER, PREMIUM, RECEIPTS, SARI, WALLET_AFTER, WALLET_BEFORE, usd } from "./data";
import { Btn, EarTag, Pill, Prov, Rule, Shell, Stamp, T, appear, mono, rise, typed } from "./ui";

export type AppCues = {
  fill: number; // fields auto-fill
  checklist: number;
  actions: number; // the two separate actions appear
  scrollTo: number; // scroll to the passbook lines
  stamp1: number;
  stamp2: number;
  receipt: number;
  payment: number; // payment recorded state
  confirm: number; // insurer confirms coverage
};

const Field: React.FC<{ k: string; v: string; t: number; at: number }> = ({ k, v, t, at }) => (
  <div style={{ padding: "6px 0", borderBottom: `1px solid ${APP.line}` }}>
    <div style={{ fontSize: 14, fontWeight: 700, color: APP.muted }}>{k}</div>
    <div style={{ ...mono, fontSize: 16.5, fontWeight: 700, minHeight: 22 }}>{typed(v, t, at, 40)}</div>
  </div>
);

const Check: React.FC<{ label: string; state: "ok" | "na"; t: number; at: number }> = ({ label, state, t, at }) => (
  <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 16, padding: "4px 0", opacity: appear(t, at) }}>
    {state === "ok" ? <CircleCheck size={18} color={APP.ok} strokeWidth={2.25} /> : <CircleMinus size={18} color={APP.muted} strokeWidth={2.25} />}
    <span style={{ color: state === "ok" ? APP.ink : APP.muted }}>{label}</span>
  </div>
);

const Line: React.FC<{ n: string; time: string; title: string; sub: string; amount: string; stampAt: number; t: number; at: number; stampText: string }> = ({ n, time, title, sub, amount, stampAt, t, at, stampText }) => {
  const done = t >= stampAt;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "54px 1fr auto",
        gap: 8,
        padding: 12,
        margin: "8px 12px",
        borderRadius: 10,
        background: done ? APP.bg : APP.tagSoft,
        border: `2px solid ${done ? APP.line : APP.tagEdge}`,
        ...rise(t, at),
      }}
    >
      <div style={{ ...mono }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>{n}</div>
        <div style={{ fontSize: 13, color: APP.muted }}>{time}</div>
      </div>
      <div>
        <div style={{ fontWeight: 700, fontSize: 16.5 }}>{title}</div>
        <div style={{ fontSize: 14.5, color: APP.muted }}>{sub}</div>
        <div style={{ marginTop: 6 }}>{done ? <Stamp kind="approved" text={stampText} press={t - stampAt} /> : <Stamp kind="awaiting" text="Awaiting your stamp" />}</div>
      </div>
      <div style={{ ...mono, fontWeight: 700, fontSize: 16 }}>{amount}</div>
    </div>
  );
};

const State: React.FC<{ label: string; sub: string; on: boolean; pending?: boolean; t: number; at: number }> = ({ label, sub, on, pending, t, at }) => (
  <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "8px 16px", opacity: appear(t, at) }}>
    {on ? <CircleCheck size={22} color={APP.ok} strokeWidth={2.25} /> : <Hourglass size={22} color={APP.awaitInk} strokeWidth={2.25} />}
    <div>
      <div style={{ fontWeight: 700, fontSize: 16.5, color: on ? APP.ok : pending ? APP.awaitInk : APP.ink }}>{label}</div>
      <div style={{ ...mono, fontSize: 13.5, color: APP.muted }}>{sub}</div>
    </div>
  </div>
);

export const ApplicationScreen: React.FC<{ t: number; c: AppCues }> = ({ t, c }) => {
  const scroll = 560 * io(clamp((t - c.scrollTo) / 0.6));
  const wallet = t >= c.payment ? WALLET_AFTER : WALLET_BEFORE;
  const badge = (t >= c.actions ? 2 : 0) - (t >= c.stamp1 ? 1 : 0) - (t >= c.stamp2 ? 1 : 0);
  const decisionPressed = (t > c.stamp1 - 0.12 && t < c.stamp1 + 0.1) || (t > c.stamp2 - 0.12 && t < c.stamp2 + 0.1);
  return (
    <Shell time="09:31" tab="approvals" badge={badge} wallet={usd(wallet)} title={<span style={{ fontWeight: 700, fontSize: 20 }}>Approvals</span>}>
      <div style={{ translate: `0 ${-scroll}px` }}>
        <div style={{ padding: "14px 16px 6px", display: "flex", alignItems: "center", gap: 10 }}>
          <EarTag num={SARI.tag} h={40} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: T.title }}>Application</div>
            <div style={{ fontSize: 14.5, color: APP.muted }}>Prepared by the VEYRA AI agent</div>
          </div>
          <Prov kind="sandbox" />
        </div>
        <div style={{ padding: "0 16px" }}>
          <Field k="Animal" v={`${SARI.name} · ${SARI.id}`} t={t} at={c.fill} />
          <Field k="Identity" v="Confirmed · 20 Oct 09:14 · A.P." t={t} at={c.fill + 0.35} />
          <Field k="Age · weight (estimates)" v="24–30 mo · 480–560 kg" t={t} at={c.fill + 0.7} />
          <Field k="Insured value" v={`${usd(INSURED_VALUE)} USD (value low bound)`} t={t} at={c.fill + 1.05} />
          <Field k="Plan" v="Basic Mortality & Accident · sample-v1" t={t} at={c.fill + 1.4} />
          <Field k="Provider" v="Sandbox Mutual (sandbox)" t={t} at={c.fill + 1.75} />
        </div>
        <div style={{ padding: "12px 16px 4px", fontWeight: 700, fontSize: 18 }}>Evidence checklist</div>
        <div style={{ padding: "0 16px" }}>
          <Check label="Muzzle reference · 0:01.5" state="ok" t={t} at={c.checklist} />
          <Check label="Body frame · 0:06.0" state="ok" t={t} at={c.checklist + 0.15} />
          <Check label={`Valuation confirmed · ${MANAGER.initials}`} state="ok" t={t} at={c.checklist + 0.3} />
          <Check label="Ownership document · not required" state="na" t={t} at={c.checklist + 0.45} />
        </div>
        <Rule w={2} color={APP.ink} style={{ margin: "14px 0 4px" }} />
        <div style={{ padding: "6px 16px 0", fontWeight: 700, fontSize: T.title }}>Passbook</div>
        <Line n="01" time="09:31" title="Policy application" sub="Basic Mortality & Accident · Sandbox Mutual" amount="—" stampAt={c.stamp1} t={t} at={c.actions} stampText={`Approved · 20 Oct 09:31 · ${MANAGER.initials}`} />
        <Line n="02" time="09:31" title="Premium payment" sub="Separate action · annual premium" amount={`−${usd(PREMIUM)}`} stampAt={c.stamp2} t={t} at={c.actions + 0.25} stampText={`Approved · 20 Oct 09:31 · ${MANAGER.initials}`} />
        <div style={{ padding: "6px 16px", borderTop: `2px solid ${APP.ink}`, margin: "6px 0 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 15.5, padding: "6px 0" }}>
            <span style={{ color: APP.muted }}>Sandbox balance after</span>
            <span style={{ ...mono, fontWeight: 700 }}>{usd(WALLET_AFTER)} USD</span>
          </div>
          {t < c.stamp2 + 0.3 ? (
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <Btn label="Approve and stamp" icon={StampIcon} h={52} pressed={decisionPressed} style={{ flex: 1 }} />
              <Btn v="danger" label="Decline" icon={X} />
            </div>
          ) : (
            <div style={{ paddingTop: 4 }}>
              <State label="Submitted" sub={`${RECEIPTS.application} · application received`} on t={t} at={c.receipt} />
              <State label="Payment recorded (sandbox)" sub={`${RECEIPTS.payment} · 87.36 USD`} on={t >= c.payment} t={t} at={c.receipt + 0.2} />
              <State
                label={t >= c.confirm ? "Coverage confirmed by insurer" : "Waiting for insurer confirmation"}
                sub={t >= c.confirm ? `${RECEIPTS.policy} · effective 20 Oct 2026` : "Payment alone does not activate cover"}
                on={t >= c.confirm}
                pending
                t={t}
                at={c.receipt + 0.4}
              />
              {t >= c.confirm ? <div style={{ padding: "4px 16px" }}><Pill tone="ok" label="Coverage active" /></div> : null}
            </div>
          )}
        </div>
      </div>
      <Tap t={t} at={c.stamp1} x={150} y={106 + 820 - 560 + 0} />
      <Tap t={t} at={c.stamp2} x={150} y={106 + 820 - 560 + 0} />
    </Shell>
  );
};
