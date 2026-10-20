// Film palette (the Product Launch Reveal reference) and the app's Ear Tag tokens (apps/web/src/styles/tokens.css).

export const FILM = {
  GV: ["#b69cff", "#e879f9", "#ff9a4d"], // violet -> orange
  GT: ["#5eead4", "#38bdf8", "#6d7cff"], // teal -> blue
  GG: ["#7cf0b8", "#2dd4bf"], // green -> teal (data confirmation)
  RED: "#ff453a",
  INK: "#f5f5f7",
  GREY: "#a1a1a6",
  DIM: "#6e6e73",
  STAGE: "#030304",
  MINT: "#7cf0b8",
} as const;

export const gradCss = (stops: readonly string[], deg = 90) => `linear-gradient(${deg}deg, ${stops.join(", ")})`;

export const APP = {
  bg: "oklch(1 0 0)",
  ink: "oklch(0.18 0.005 260)",
  muted: "oklch(0.42 0.01 260)",
  line: "oklch(0.82 0.006 260)",
  lineStrong: "oklch(0.6 0.01 260)",
  surface: "oklch(0.975 0.002 260)",
  surface2: "oklch(0.95 0.003 260)",
  shell: "oklch(0.17 0 0)",
  shell2: "oklch(0.27 0 0)",
  onShell: "oklch(1 0 0)",
  onShellMuted: "oklch(0.82 0 0)",
  shellLine: "oklch(0.36 0 0)",
  tag: "oklch(0.86 0.17 92)",
  tagPressed: "oklch(0.8 0.16 88)",
  tagEdge: "oklch(0.6 0.12 80)",
  tagSoft: "oklch(0.97 0.06 95)",
  awaitInk: "oklch(0.42 0.09 75)",
  ok: "oklch(0.47 0.12 155)",
  okSoft: "oklch(0.95 0.04 155)",
  danger: "oklch(0.5 0.19 28)",
  dangerSoft: "oklch(0.95 0.03 25)",
  uncertain: "oklch(0.56 0.15 50)",
  uncertainInk: "oklch(0.48 0.13 50)",
  uncertainSoft: "oklch(0.95 0.04 65)",
} as const;

export const FONT = {
  film: '"Inter", system-ui, sans-serif',
  sans: '"Atkinson Hyperlegible Next", system-ui, sans-serif',
  mono: '"Atkinson Hyperlegible Mono", ui-monospace, monospace',
} as const;
