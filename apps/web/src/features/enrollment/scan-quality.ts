/**
 * A capture-quality hint for the muzzle guide box: is the picture sharp, lit, and steady enough to be worth
 * recording? It reads only pixels (no model), so it says nothing about who the animal is. It is NOT identity
 * confidence; the matcher decides identity on the server.
 *
 * Sharpness is the variance of the 4-neighbour Laplacian of the greyscale box (edge energy: the muzzle's ridges
 * and beads give a sharp, close capture a high variance; blur or a far-away muzzle gives a low one), mapped to
 * 0..1 on a log scale. Brightness is the mean grey level. Motion is the mean absolute difference from the
 * previous sample of the same box.
 */

export type QualityStatus = "good" | "dark" | "bright" | "moving" | "soft";

export interface ScanQuality {
  /** 0..1: what the meter fills to. */
  score: number;
  /** 0..1 from the Laplacian variance. */
  sharpness: number;
  /** The raw Laplacian variance (grey levels squared). */
  laplacianVariance: number;
  /** Mean grey level, 0..255. */
  brightness: number;
  /** Mean absolute grey difference from the previous sample, 0..255; null on the first sample. */
  motion: number | null;
  status: QualityStatus;
}

/** Laplacian variance at or below this reads as no detail at all; at or above `SHARP_VARIANCE`, fully sharp. */
export const SOFT_VARIANCE = 15;
export const SHARP_VARIANCE = 400;
/** The sharpness a muzzle capture should reach. */
export const SHARP_ENOUGH = 0.6;
export const DARK_BELOW = 50;
export const BRIGHT_ABOVE = 225;
export const MOVING_ABOVE = 20;
/** Width the guide box is sampled at; small enough to score every 250 ms on a phone. */
export const SAMPLE_WIDTH = 160;

export const STATUS_COPY: Record<QualityStatus, string> = {
  good: "Hold steady · muzzle sharp enough",
  dark: "Too dark · find more light",
  bright: "Too bright · shade the muzzle",
  moving: "Hold steady · the picture is moving",
  soft: "Move closer · fill the box with the muzzle",
};

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

/** Luma (BT.601) of RGBA pixels. */
export function toGray(rgba: ArrayLike<number>, width: number, height: number): Float32Array {
  const gray = new Float32Array(width * height);
  for (let i = 0, p = 0; i < gray.length; i++, p += 4) {
    gray[i] = 0.299 * rgba[p]! + 0.587 * rgba[p + 1]! + 0.114 * rgba[p + 2]!;
  }
  return gray;
}

export function meanOf(gray: ArrayLike<number>): number {
  if (gray.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < gray.length; i++) sum += gray[i]!;
  return sum / gray.length;
}

/** Variance of the 4-neighbour Laplacian over the interior pixels. */
export function laplacianVariance(gray: ArrayLike<number>, width: number, height: number): number {
  if (width < 3 || height < 3) return 0;
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < height - 1; y++) {
    const row = y * width;
    for (let x = 1; x < width - 1; x++) {
      const i = row + x;
      const lap = 4 * gray[i]! - gray[i - 1]! - gray[i + 1]! - gray[i - width]! - gray[i + width]!;
      sum += lap;
      sumSq += lap * lap;
      n++;
    }
  }
  const mean = sum / n;
  return Math.max(0, sumSq / n - mean * mean);
}

export function meanAbsDiff(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length || a.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += Math.abs(a[i]! - b[i]!);
  return sum / a.length;
}

export function sharpnessFrom(variance: number): number {
  const lo = Math.log10(1 + SOFT_VARIANCE);
  const hi = Math.log10(1 + SHARP_VARIANCE);
  return clamp01((Math.log10(1 + variance) - lo) / (hi - lo));
}

/** Score one greyscale sample of the guide box, against the previous sample for motion when there is one. */
export function scoreGray(gray: ArrayLike<number>, width: number, height: number, previous?: ArrayLike<number> | null): ScanQuality {
  const variance = laplacianVariance(gray, width, height);
  const sharpness = sharpnessFrom(variance);
  const brightness = meanOf(gray);
  const motion = previous && previous.length === gray.length ? meanAbsDiff(gray, previous) : null;
  const exposure = clamp01(Math.min((brightness - 25) / (DARK_BELOW - 25), (255 - brightness) / (255 - BRIGHT_ABOVE)));
  const steadiness = motion === null ? 1 : clamp01(1 - (motion - MOVING_ABOVE) / 30);
  const status: QualityStatus =
    brightness < DARK_BELOW
      ? "dark"
      : brightness > BRIGHT_ABOVE
        ? "bright"
        : motion !== null && motion > MOVING_ABOVE
          ? "moving"
          : sharpness < SHARP_ENOUGH
            ? "soft"
            : "good";
  return { score: clamp01(sharpness * exposure * steadiness), sharpness, laplacianVariance: variance, brightness, motion, status };
}

/** Score RGBA pixels (an `ImageData`). */
export function scoreImage(image: { data: ArrayLike<number>; width: number; height: number }, previous?: ArrayLike<number> | null) {
  const gray = toGray(image.data, image.width, image.height);
  return { quality: scoreGray(gray, image.width, image.height, previous), gray };
}

/** Ease the meter toward the newest score so it fills rather than flickers; the status is always the newest. */
export function smoothQuality(previous: ScanQuality | null, next: ScanQuality, alpha = 0.45): ScanQuality {
  if (!previous) return next;
  return { ...next, score: previous.score + alpha * (next.score - previous.score) };
}
