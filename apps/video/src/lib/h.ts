// Port of the brief's H helper library (lib/harness.js): seeded randomness, gradient noise, math, easing, colour.
// Every frame is a pure function of time, so all randomness comes from H.rng(seed) / H.makeNoise(seed).

export type Rng = (() => number) & {
  range: (lo: number, hi: number) => number;
  int: (lo: number, hi: number) => number;
  pick: <T>(arr: readonly T[]) => T;
  chance: (p: number) => boolean;
  gauss: () => number;
};

function hashStr(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export const rng = (seed: number | string = 1): Rng => {
  let a = typeof seed === "string" ? hashStr(seed) : seed >>> 0 || 1;
  const r = (() => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }) as Rng;
  r.range = (lo, hi) => lo + r() * (hi - lo);
  r.int = (lo, hi) => Math.floor(lo + r() * (hi - lo + 1));
  r.pick = (arr) => arr[Math.floor(r() * arr.length)];
  r.chance = (p) => r() < p;
  r.gauss = () => {
    let u = 0,
      v = 0;
    while (!u) u = r();
    while (!v) v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
  return r;
};

export const makeNoise = (seed = 1) => {
  const r = rng(seed),
    p = new Uint8Array(512),
    perm = [...Array(256).keys()];
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [perm[i], perm[j]] = [perm[j], perm[i]];
  }
  for (let i = 0; i < 512; i++) p[i] = perm[i & 255];
  const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
  const lerp_ = (a: number, b: number, t: number) => a + (b - a) * t;
  const g3 = (h: number, x: number, y: number, z: number) => {
    h &= 15;
    const u = h < 8 ? x : y,
      v = h < 4 ? y : h === 12 || h === 14 ? x : z;
    return (h & 1 ? -u : u) + (h & 2 ? -v : v);
  };
  function n3(x: number, y: number, z: number) {
    const X = Math.floor(x) & 255,
      Y = Math.floor(y) & 255,
      Z = Math.floor(z) & 255;
    x -= Math.floor(x);
    y -= Math.floor(y);
    z -= Math.floor(z);
    const u = fade(x),
      v = fade(y),
      w = fade(z);
    const A = p[X] + Y,
      AA = p[A] + Z,
      AB = p[A + 1] + Z,
      B = p[X + 1] + Y,
      BA = p[B] + Z,
      BB = p[B + 1] + Z;
    return lerp_(
      lerp_(lerp_(g3(p[AA], x, y, z), g3(p[BA], x - 1, y, z), u), lerp_(g3(p[AB], x, y - 1, z), g3(p[BB], x - 1, y - 1, z), u), v),
      lerp_(
        lerp_(g3(p[AA + 1], x, y, z - 1), g3(p[BA + 1], x - 1, y, z - 1), u),
        lerp_(g3(p[AB + 1], x, y - 1, z - 1), g3(p[BB + 1], x - 1, y - 1, z - 1), u),
        v,
      ),
      w,
    );
  }
  const n2 = (x: number, y: number) => n3(x, y, 0.5);
  const fbm3 = (x: number, y: number, z: number, oct = 4) => {
    let s = 0,
      a = 0.5,
      f = 1,
      norm = 0;
    for (let i = 0; i < oct; i++) {
      s += a * n3(x * f, y * f, z * f);
      norm += a;
      a *= 0.5;
      f *= 2;
    }
    return s / norm;
  };
  const fbm2 = (x: number, y: number, oct = 4) => fbm3(x, y, 0.5, oct);
  return { n2, n3, fbm2, fbm3 };
};

// ---------- math ----------
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
export const map = (v: number, a: number, b: number, c: number, d: number) => c + ((v - a) / (b - a)) * (d - c);
export const smooth = (e0: number, e1: number, x: number) => {
  const t = clamp((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};
export const ease = {
  inOut: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  out: (t: number) => 1 - Math.pow(1 - t, 3),
  in: (t: number) => t * t * t,
  back: (t: number) => {
    const c = 1.70158;
    return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
  },
};
// the reference's shorthands
export const sm = (a: number, b: number, x: number) => smooth(a, b, x);
export const io = (x: number) => ease.inOut(clamp(x));
export const eo = (x: number) => ease.out(clamp(x));
export const gauss = (d: number, k: number) => Math.exp(-d * d * k);

// ---------- colour ----------
export const hex = (h: string): [number, number, number] => {
  h = h.replace("#", "");
  if (h.length === 3)
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
export const rgba = (c: string | number[], a = 1) => {
  const [r, g, b] = Array.isArray(c) ? c : hex(c);
  return `rgba(${r | 0},${g | 0},${b | 0},${a})`;
};
export const mix = (c1: string | number[], c2: string | number[], t: number) => {
  const a = Array.isArray(c1) ? c1 : hex(c1),
    b = Array.isArray(c2) ? c2 : hex(c2);
  return [0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * t);
};

// keyframed camera, as in the reference's keyed(): eased (inOut cubic) interpolation of every numeric field
export function keyed<K extends { t: number }>(keys: readonly K[], t: number): K {
  if (t <= keys[0].t) return { ...keys[0] };
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i],
      b = keys[i + 1];
    if (t <= b.t) {
      const e = io((t - a.t) / (b.t - a.t));
      const o = {} as Record<string, number>;
      for (const k in a) o[k] = lerp(a[k] as number, b[k] as number, e);
      return o as unknown as K;
    }
  }
  return { ...keys[keys.length - 1] };
}

// pulse that decays after each time in `pulses` (the reference's ringGlow)
export function ringGlow(base: number, t: number, pulses: readonly number[]) {
  let v = base;
  for (const p of pulses) if (t > p) v += 0.9 * Math.exp(-(t - p) * 5);
  return v;
}
