import React from "react";
import {
  CircleCheck,
  CircleMinus,
  CircleX,
  Hourglass,
  TriangleAlert,
  ClipboardList,
  ScanLine,
  Cctv,
  Stamp as StampIcon,
  Menu,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { APP, FONT } from "../theme";
import { clamp, eo } from "../lib/h";

// Recreations of the VEYRA app's "Ear Tag" design system (apps/web/src/styles/tokens.css):
// white ground, near-black ink, black shell bar + bottom tabs, tag-yellow ear tags as identity, double-ruled
// mono stamps, Atkinson Hyperlegible Next/Mono. Sized up ~15 % from the app's ramp so they read on video.

export const T = { h1: 30, title: 23, body: 18, label: 15, mono: 17 } as const;

export const sans: React.CSSProperties = { fontFamily: FONT.sans };
export const mono: React.CSSProperties = { fontFamily: FONT.mono, fontVariantNumeric: "tabular-nums slashed-zero" };

const OUTLINE = "M41 3H71Q83 3 85.5 14C87.5 23 108 24 108 41V57Q108 77 88 77H24Q4 77 4 57V41C4 24 24.5 23 26.5 14Q29 3 41 3Z";
const HOLE = "M62.5 16A6.5 6.5 0 1 0 49.5 16A6.5 6.5 0 1 0 62.5 16Z";

export type TagState = "confirmed" | "pending" | "none";
export const EarTag: React.FC<{ num?: string; state?: TagState; h?: number; style?: React.CSSProperties }> = ({ num = "---", state = "confirmed", h = 40, style }) => {
  const fill = state === "confirmed" ? APP.tag : state === "pending" ? APP.bg : APP.surface2;
  const stroke = state === "confirmed" ? APP.tagEdge : state === "pending" ? APP.ink : APP.lineStrong;
  const sw = state === "pending" ? 2.5 : 1.5;
  const fs = h * (state === "none" ? 0.3 : 0.42);
  return (
    <span style={{ position: "relative", display: "inline-grid", placeItems: "end center", height: h, aspectRatio: "112 / 80", flex: "none", ...style }}>
      <svg viewBox="0 0 112 80" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", overflow: "visible" }}>
        <path d={`${OUTLINE}${HOLE}`} fillRule="evenodd" fill={fill} />
        <path d={OUTLINE} fill="none" stroke={stroke} strokeWidth={sw} strokeDasharray={state === "pending" ? "6 4" : undefined} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        <path d={HOLE} fill="none" stroke={stroke} strokeWidth={state === "pending" ? 2 : sw} vectorEffect="non-scaling-stroke" />
      </svg>
      <span
        style={{
          position: "relative",
          paddingBottom: state === "none" ? "14%" : "11%",
          ...(state === "none" ? { ...sans, fontWeight: 700, color: APP.muted } : { ...mono, fontWeight: 700, letterSpacing: "0.02em", color: APP.ink }),
          fontSize: fs,
          lineHeight: 1,
        }}
      >
        {state === "none" ? "no tag" : num}
      </span>
    </span>
  );
};

export type Tone = "ok" | "danger" | "uncertain" | "neutral" | "awaiting";
const TONE: Record<Tone, { bg: string; fg: string; border?: string; icon: LucideIcon }> = {
  ok: { bg: APP.okSoft, fg: APP.ok, icon: CircleCheck },
  danger: { bg: APP.dangerSoft, fg: APP.danger, icon: CircleX },
  uncertain: { bg: APP.uncertainSoft, fg: APP.uncertainInk, icon: TriangleAlert },
  neutral: { bg: "transparent", fg: APP.muted, border: `2px solid ${APP.line}`, icon: CircleMinus },
  awaiting: { bg: APP.tagSoft, fg: APP.awaitInk, border: `1px solid ${APP.tagEdge}`, icon: Hourglass },
};

export const Pill: React.FC<{ tone: Tone; label: string; icon?: LucideIcon; size?: number; style?: React.CSSProperties }> = ({ tone, label, icon, size = 1, style }) => {
  const c = TONE[tone];
  const Icon = icon ?? c.icon;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6 * size,
        height: 32 * size,
        padding: `0 ${12 * size}px`,
        borderRadius: 999,
        background: c.bg,
        color: c.fg,
        border: c.border,
        ...sans,
        fontWeight: 700,
        fontSize: T.label * size,
        whiteSpace: "nowrap",
        boxSizing: "border-box",
        ...style,
      }}
    >
      <Icon size={17 * size} strokeWidth={2.25} />
      {label}
    </span>
  );
};

export type ProvKind = "live" | "prototype" | "simulated" | "documented" | "sandbox";
export const Prov: React.FC<{ kind: ProvKind; style?: React.CSSProperties }> = ({ kind, style }) => {
  const look: Record<ProvKind, React.CSSProperties> = {
    live: { background: APP.ok, color: "#fff", border: `2px solid ${APP.ok}` },
    prototype: { background: APP.bg, color: APP.ink, border: `2px solid ${APP.ink}` },
    simulated: { background: APP.bg, color: APP.muted, border: `2px dashed ${APP.lineStrong}` },
    documented: { background: APP.surface2, color: APP.muted, border: `2px solid ${APP.surface2}` },
    sandbox: { background: APP.bg, color: APP.muted, border: `2px dashed ${APP.lineStrong}` },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 26,
        padding: "0 10px",
        borderRadius: 999,
        ...sans,
        fontWeight: 700,
        fontSize: 13.5,
        whiteSpace: "nowrap",
        boxSizing: "border-box",
        ...look[kind],
        ...style,
      }}
    >
      {kind}
    </span>
  );
};

export type StampKind = "approved" | "posted" | "declined" | "failed" | "unknown" | "confirmed" | "awaiting";
/** Crisp 4px double-ruled stamp, never rotated. `press` = seconds since it landed (plays the 180 ms press). */
export const Stamp: React.FC<{ kind: StampKind; text: string; press?: number; size?: number; style?: React.CSSProperties }> = ({ kind, text, press, size = 1, style }) => {
  const color = kind === "posted" || kind === "confirmed" ? APP.ok : kind === "declined" || kind === "failed" ? APP.danger : kind === "unknown" ? APP.uncertainInk : kind === "awaiting" ? APP.awaitInk : APP.ink;
  const p = press == null ? 1 : eo(clamp(press / 0.18));
  const awaiting = kind === "awaiting";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: `${3 * size}px ${9 * size}px`,
        border: awaiting ? `2px dashed ${color}` : `${4 * size}px double ${color}`,
        borderRadius: 4,
        background: awaiting ? "transparent" : APP.bg,
        color,
        ...mono,
        fontSize: 13.5 * size,
        fontWeight: 700,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
        opacity: press == null ? 1 : 0.35 + 0.65 * p,
        scale: String(press == null ? 1 : 1.06 - 0.06 * p),
        boxShadow: press != null && p < 1 ? `0 6px 14px rgba(20,20,30,${0.22 * (1 - p)})` : undefined,
        ...style,
      }}
    >
      {text}
    </span>
  );
};

export type BtnVariant = "primary" | "secondary" | "danger" | "ghost" | "disabled";
export const Btn: React.FC<{ v?: BtnVariant; label: string; icon?: LucideIcon; h?: number; full?: boolean; pressed?: boolean; style?: React.CSSProperties }> = ({
  v = "primary",
  label,
  icon: Icon,
  h = 48,
  full,
  pressed,
  style,
}) => {
  const look: Record<BtnVariant, React.CSSProperties> = {
    primary: { background: pressed ? APP.shell2 : APP.ink, color: APP.tag, border: `2px solid ${APP.ink}` },
    secondary: { background: pressed ? APP.surface2 : APP.bg, color: APP.ink, border: `2px solid ${APP.ink}` },
    danger: { background: APP.bg, color: APP.danger, border: `2px solid ${APP.danger}` },
    ghost: { background: "transparent", color: APP.ink, border: "2px solid transparent" },
    disabled: { background: APP.surface2, color: APP.muted, border: `2px solid ${APP.surface2}` },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        height: h,
        padding: "0 18px",
        borderRadius: 10,
        width: full ? "100%" : undefined,
        boxSizing: "border-box",
        ...sans,
        fontWeight: 700,
        fontSize: T.body,
        whiteSpace: "nowrap",
        translate: pressed ? "0 1px" : undefined,
        ...look[v],
        ...style,
      }}
    >
      {Icon ? <Icon size={20} strokeWidth={2.25} /> : null}
      {label}
    </span>
  );
};

/** A registered evidence frame: 10 px corners and four drawn registration brackets. */
export const EvidenceFrame: React.FC<{ w: number; h: number; children?: React.ReactNode; missing?: string; caption?: string; style?: React.CSSProperties }> = ({
  w,
  h,
  children,
  missing,
  caption,
  style,
}) => {
  const b = 14;
  const br = (pos: React.CSSProperties, bt: string) => <div style={{ position: "absolute", width: b, height: b, ...pos, borderColor: APP.ink, borderStyle: "solid", borderWidth: bt }} />;
  return (
    <div style={{ position: "relative", width: w, height: h, borderRadius: 10, overflow: "hidden", background: missing ? APP.surface2 : "#111", border: missing ? `2px dashed ${APP.lineStrong}` : undefined, boxSizing: "border-box", ...style }}>
      {children}
      {missing ? (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", ...sans, fontWeight: 700, color: APP.muted, fontSize: 15, textAlign: "center", padding: 8 }}>{missing}</div>
      ) : (
        <>
          {br({ left: 5, top: 5 }, "2.5px 0 0 2.5px")}
          {br({ right: 5, top: 5 }, "2.5px 2.5px 0 0")}
          {br({ left: 5, bottom: 5 }, "0 0 2.5px 2.5px")}
          {br({ right: 5, bottom: 5 }, "0 2.5px 2.5px 0")}
        </>
      )}
      {caption ? (
        <span style={{ position: "absolute", left: 8, bottom: 8, padding: "2px 8px", borderRadius: 6, background: "rgba(20,20,24,0.82)", color: "#fff", ...sans, fontWeight: 700, fontSize: 13.5 }}>{caption}</span>
      ) : null}
    </div>
  );
};

export const Rule: React.FC<{ w?: number; color?: string; style?: React.CSSProperties }> = ({ w = 1, color = APP.line, style }) => <div style={{ height: w, background: color, ...style }} />;

/** VEYRA mark: the small solid ear tag */
export const TagLogo: React.FC<{ h?: number }> = ({ h = 26 }) => (
  <svg viewBox="0 0 28 34" style={{ height: h, width: (h * 28) / 34 }}>
    <path
      d="M10 1.5H18Q21.5 1.5 22.2 5C22.8 8.2 26.5 8.6 26.5 14V25.5Q26.5 32.5 19.5 32.5H8.5Q1.5 32.5 1.5 25.5V14C1.5 8.6 5.2 8.2 5.8 5Q6.5 1.5 10 1.5ZM17 7.5A3 3 0 1 0 11 7.5A3 3 0 1 0 17 7.5Z"
      fill={APP.tag}
      fillRule="evenodd"
    />
  </svg>
);

export type Tab = "herd" | "enroll" | "monitor" | "approvals" | "more";
const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: "herd", label: "Herd", icon: ClipboardList },
  { id: "enroll", label: "Enroll", icon: ScanLine },
  { id: "monitor", label: "Monitor", icon: Cctv },
  { id: "approvals", label: "Approvals", icon: StampIcon },
  { id: "more", label: "More", icon: Menu },
];

/**
 * The phone shell: status bar + black top bar (logo, wordmark, sandbox wallet) + white content +
 * black bottom tabs. `scroll` moves the content up by that many px.
 */
export const Shell: React.FC<{
  time?: string;
  tab?: Tab;
  badge?: number;
  wallet?: string;
  title?: React.ReactNode;
  scroll?: number;
  children: React.ReactNode;
  dark?: boolean;
  noTabs?: boolean;
}> = ({ time = "09:12", tab = "herd", badge, wallet = "10,000.00", title, scroll = 0, children, dark, noTabs }) => (
  <div style={{ position: "absolute", inset: 0, background: dark ? "#000" : APP.bg, overflow: "hidden", ...sans, color: APP.ink }}>
    <div style={{ position: "absolute", top: 106, left: 0, right: 0, bottom: noTabs ? 26 : 82, overflow: "hidden" }}>
      <div style={{ translate: `0 ${-scroll}px` }}>{children}</div>
    </div>
    {/* top: status bar + shell bar */}
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 106, background: APP.shell, color: APP.onShell }}>
      <div style={{ position: "absolute", left: 34, top: 16, ...sans, fontWeight: 700, fontSize: 16 }}>{time}</div>
      <div style={{ position: "absolute", right: 28, top: 18, display: "flex", gap: 5, alignItems: "flex-end" }}>
        {[6, 9, 12, 15].map((hh) => (
          <div key={hh} style={{ width: 4, height: hh, background: "#fff", borderRadius: 1 }} />
        ))}
        <div style={{ width: 24, height: 12, border: "1.5px solid #fff", borderRadius: 3, marginLeft: 6, padding: 1, boxSizing: "border-box" }}>
          <div style={{ width: "78%", height: "100%", background: "#fff", borderRadius: 1 }} />
        </div>
      </div>
      <div style={{ position: "absolute", left: 18, right: 16, top: 54, height: 46, display: "flex", alignItems: "center", gap: 10 }}>
        <TagLogo h={28} />
        {title ?? <span style={{ fontWeight: 800, fontSize: 21, letterSpacing: "0.02em" }}>VEYRA</span>}
        <span style={{ flex: 1 }} />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 34, padding: "0 10px", borderRadius: 10, border: `2px solid ${APP.shellLine}`, ...mono, fontSize: 14.5, fontWeight: 700 }}>
          <Wallet size={16} strokeWidth={2.25} />
          {wallet}
        </span>
      </div>
    </div>
    {/* bottom tabs */}
    {noTabs ? (
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 26, background: APP.shell }} />
    ) : (
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 82, background: APP.shell, color: APP.onShell }}>
        <div style={{ display: "flex", height: 56, padding: "4px 6px 0", gap: 4 }}>
          {TABS.map((tb) => {
            const on = tb.id === tab;
            return (
              <div
                key={tb.id}
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 2,
                  borderRadius: 10,
                  background: on ? APP.tag : "transparent",
                  color: on ? APP.ink : APP.onShell,
                  fontWeight: 700,
                  fontSize: 12.5,
                  position: "relative",
                }}
              >
                <tb.icon size={20} strokeWidth={2.25} />
                {tb.label}
                {tb.id === "approvals" && badge ? (
                  <span style={{ position: "absolute", top: 2, right: 10, minWidth: 18, height: 18, borderRadius: 9, background: on ? APP.ink : APP.tag, color: on ? APP.tag : APP.ink, ...mono, fontSize: 12, fontWeight: 700, display: "grid", placeItems: "center" }}>
                    {badge}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", left: "50%", bottom: 8, width: 134, height: 5, borderRadius: 3, background: "#fff", translate: "-50% 0" }} />
      </div>
    )}
  </div>
);

/** typing reveal for in-app text fields: shows the first n chars at time t */
export const typed = (text: string, t: number, t0: number, cps = 16) => text.slice(0, Math.max(0, Math.floor((t - t0) * cps)));

/** 0..1 appear helper for in-app elements (quick ease-out, 0.35 s) */
export const appear = (t: number, t0: number, d = 0.35) => eo(clamp((t - t0) / d));
export const rise = (t: number, t0: number, d = 0.35, px = 14): React.CSSProperties => {
  const e = appear(t, t0, d);
  return { opacity: e, translate: `0 ${(1 - e) * px}px` };
};
