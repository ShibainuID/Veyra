import React from "react";
import { ArrowUp, CircleCheck, Sparkles, TriangleAlert } from "lucide-react";
import { APP } from "../theme";
import { clamp, io } from "../lib/h";
import { Tap } from "../components/Phone";
import { PLANS } from "./data";
import { Btn, EarTag, Pill, Shell, appear, mono } from "./ui";

// The in-app VEYRA AI agent: a conversation that does the preparation while the farmer keeps control.
export type Msg = { at: number; from: "agent" | "user"; h: number; body: (t: number) => React.ReactNode };

const VIEW_H = 656 - 56 - 64; // content viewport between the agent header and the composer

const Bubble: React.FC<{ from: "agent" | "user"; children: React.ReactNode }> = ({ from, children }) =>
  from === "user" ? (
    <div style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{ maxWidth: 290, background: APP.ink, color: "#fff", borderRadius: "16px 16px 4px 16px", padding: "10px 14px", fontSize: 17, lineHeight: 1.35 }}>{children}</div>
    </div>
  ) : (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
      <div style={{ width: 30, height: 30, borderRadius: 15, background: APP.ink, display: "grid", placeItems: "center", flex: "none" }}>
        <Sparkles size={16} color={APP.tag} strokeWidth={2.25} />
      </div>
      <div style={{ flex: 1, minWidth: 0, background: APP.surface, border: `2px solid ${APP.line}`, borderRadius: "4px 16px 16px 16px", padding: "10px 12px", fontSize: 17, lineHeight: 1.35 }}>{children}</div>
    </div>
  );

/** "typing" text reveal for agent prose */
export const say = (s: string, t: number, t0: number, cps = 55) => {
  const n = Math.floor((t - t0) * cps);
  return n >= s.length ? s : s.slice(0, Math.max(0, n)) + (n >= 0 ? "▍" : "");
};

export const AgentScreen: React.FC<{ t: number; title: string; tag: string; msgs: Msg[]; composer?: string; taps?: { at: number; x: number; y: number }[]; time?: string }> = ({
  t,
  title,
  tag,
  msgs,
  composer = "",
  taps = [],
  time = "09:20",
}) => {
  const shown = msgs.filter((m) => t >= m.at - 0.05);
  // auto-scroll: ease to keep the newest message in view
  let scroll = 0;
  let y = 12;
  for (const m of msgs) {
    y += m.h + 12;
    if (t >= m.at) {
      const target = Math.max(0, y - VIEW_H);
      scroll = scroll + (target - scroll) * io(clamp((t - m.at) / 0.45));
    }
  }
  return (
    <Shell time={time} tab="more" title={<span style={{ fontWeight: 700, fontSize: 20 }}>Insurance</span>}>
      {/* agent header */}
      <div style={{ position: "relative", height: 56, display: "flex", alignItems: "center", gap: 10, padding: "0 16px", borderBottom: `3px solid ${APP.ink}`, background: APP.bg, zIndex: 2 }}>
        <Sparkles size={22} strokeWidth={2.25} />
        <span style={{ fontWeight: 700, fontSize: 19 }}>VEYRA AI agent</span>
        <span style={{ flex: 1 }} />
        <EarTag num={tag} h={30} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>{title}</span>
      </div>
      <div style={{ position: "relative", height: VIEW_H, overflow: "hidden" }}>
        <div style={{ translate: `0 ${-scroll}px`, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
          {shown.map((m, i) => (
            <div key={i} style={{ minHeight: m.h, opacity: appear(t, m.at, 0.3), translate: `0 ${(1 - appear(t, m.at, 0.3)) * 10}px` }}>
              <Bubble from={m.from}>{m.body(t)}</Bubble>
            </div>
          ))}
        </div>
      </div>
      {/* composer */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 56 + VIEW_H, height: 64, borderTop: `1px solid ${APP.line}`, display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: APP.bg }}>
        <div style={{ flex: 1, height: 44, borderRadius: 10, border: `2px solid ${composer ? APP.ink : APP.lineStrong}`, display: "flex", alignItems: "center", padding: "0 12px", fontSize: 17, color: composer ? APP.ink : APP.muted }}>
          {composer || "Ask the agent…"}
        </div>
        <div style={{ width: 44, height: 44, borderRadius: 10, background: APP.ink, display: "grid", placeItems: "center" }}>
          <ArrowUp size={22} color={APP.tag} strokeWidth={2.5} />
        </div>
      </div>
      {taps.map((tp, i) => (
        <Tap key={i} t={t} at={tp.at} x={tp.x} y={tp.y} />
      ))}
    </Shell>
  );
};

/** compact plan rows inside the chat */
export const PlanRows: React.FC<{ t: number; t0: number }> = ({ t, t0 }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
    {PLANS.map((p, i) => (
      <div key={p.id} style={{ opacity: appear(t, t0 + i * 0.15), border: `2px solid ${p.status === "eligible" ? APP.ink : APP.line}`, borderRadius: 10, padding: "8px 10px", background: APP.bg }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>{p.name}</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
          <Pill tone={p.status === "eligible" ? "ok" : p.status === "review" ? "uncertain" : "danger"} label={p.statusLabel} size={0.8} />
          <span style={{ ...mono, fontSize: 15, fontWeight: 700 }}>{p.premium}</span>
        </div>
      </div>
    ))}
  </div>
);

export const Reason: React.FC<{ ok?: boolean; children: React.ReactNode }> = ({ ok = true, children }) => (
  <div style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: 15.5, marginTop: 5, color: ok ? APP.ink : APP.uncertainInk }}>
    {ok ? <CircleCheck size={17} color={APP.ok} strokeWidth={2.25} style={{ flex: "none", marginTop: 2 }} /> : <TriangleAlert size={17} color={APP.uncertain} strokeWidth={2.25} style={{ flex: "none", marginTop: 2 }} />}
    <span>{children}</span>
  </div>
);

export { Btn };
