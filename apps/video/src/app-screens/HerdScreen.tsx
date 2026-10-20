import React from "react";
import { BellRing, Check, ChevronRight, ScanLine } from "lucide-react";
import { APP } from "../theme";
import { Animal, FARM, HERD, SARI, valueRange } from "./data";
import { Btn, EarTag, mono, Pill, Rule, Shell, T, TagLogo, appear, rise } from "./ui";

export const LaunchScreen: React.FC<{ t: number; t0: number }> = ({ t, t0 }) => {
  const e = appear(t, t0, 0.6);
  return (
    <div style={{ position: "absolute", inset: 0, background: APP.shell, display: "grid", placeItems: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18, opacity: e, scale: String(0.94 + 0.06 * e) }}>
        <TagLogo h={92} />
        <div style={{ color: "#fff", fontFamily: "Atkinson Hyperlegible Next", fontWeight: 800, fontSize: 40, letterSpacing: "0.04em" }}>VEYRA</div>
      </div>
    </div>
  );
};

const Row: React.FC<{ a: Animal; hi?: boolean; style?: React.CSSProperties }> = ({ a, hi, style }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12, height: 86, padding: "0 16px", background: hi ? APP.surface2 : APP.bg, ...style }}>
    <EarTag num={a.tag} state="confirmed" h={44} />
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 19 }}>{a.name}</span>
        {a.coverage === "covered" ? <Pill tone="ok" label="Covered" /> : <Pill tone="danger" label="Not insured" />}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, color: APP.muted, fontSize: 14.5, ...mono }}>
        <span>{a.id}</span>
        <span style={{ color: APP.ink }}>{valueRange(a)} USD</span>
      </div>
      {a.alert ? (
        <div style={{ marginTop: 6 }}>
          <Pill tone={a.alert.tone} label={a.alert.label} size={0.85} />
        </div>
      ) : null}
    </div>
  </div>
);

/**
 * Herd: the seeded animals with indicative value, coverage and alerts. `withSari` adds the newly enrolled
 * cow on top (Not insured). `focus` highlights a row by tag. `scroll` in px.
 */
export const HerdScreen: React.FC<{ t: number; t0?: number; withSari?: boolean; focus?: string; time?: string; enrollTap?: boolean }> = ({
  t,
  t0 = -10,
  withSari,
  focus,
  time = "09:02",
  enrollTap,
}) => {
  const rows = withSari ? [SARI, ...HERD] : HERD;
  const uninsured = rows.filter((r) => r.coverage === "none").length;
  return (
    <Shell time={time} tab="herd">
      <div style={{ padding: "18px 16px 10px" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <span style={{ fontWeight: 700, fontSize: T.h1 }}>Herd</span>
          <span style={{ ...mono, color: APP.muted, fontSize: 15 }}>{FARM}</span>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          {[
            { l: "All", n: rows.length, on: true },
            { l: "Not insured", n: uninsured },
            { l: "Alerts", n: rows.filter((r) => r.alert).length },
          ].map((c) => (
            <span
              key={c.l}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                height: 40,
                padding: "0 12px",
                borderRadius: 10,
                border: `2px solid ${APP.ink}`,
                background: c.on ? APP.ink : APP.bg,
                color: c.on ? APP.bg : APP.ink,
                fontWeight: 700,
                fontSize: 15,
              }}
            >
              {c.on ? <Check size={15} strokeWidth={2.5} /> : null}
              {c.l}
              <span style={{ ...mono }}>{c.n}</span>
            </span>
          ))}
        </div>
      </div>
      <Rule w={3} color={APP.ink} style={{ margin: "6px 0 0" }} />
      {rows.map((a, i) => (
        <React.Fragment key={a.id}>
          <Row a={a} hi={focus === a.tag} style={rise(t, t0 + i * 0.08)} />
          <Rule />
        </React.Fragment>
      ))}
      <div style={{ padding: 16, display: "flex", gap: 10, alignItems: "center" }}>
        <Btn label="Enroll a cow" icon={ScanLine} pressed={enrollTap} />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: APP.muted, fontWeight: 700, fontSize: 15 }}>
          <BellRing size={17} strokeWidth={2.25} /> 1 alert <ChevronRight size={16} />
        </span>
      </div>
    </Shell>
  );
};

export const HERD_ROW_Y = (i: number) => 106 + 18 + 36 + 14 + 40 + 10 + 9 + i * 87; // first row top inside the screen
