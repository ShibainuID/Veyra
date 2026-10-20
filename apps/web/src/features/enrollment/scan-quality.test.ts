import { describe, expect, it } from "vitest";
import {
  SHARP_ENOUGH,
  laplacianVariance,
  meanOf,
  scoreGray,
  scoreImage,
  sharpnessFrom,
  smoothQuality,
  toGray,
} from "./scan-quality";

const W = 160;
const H = 136;

/** A deterministic textured grey image (a stand-in for muzzle ridges): mean `level`, spread `contrast`. */
function texture(level: number, contrast: number, seed = 7): Float32Array {
  let state = seed;
  const rand = () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
  const out = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const ridge = Math.sin(x * 0.9) * Math.cos(y * 0.7);
      out[y * W + x] = Math.min(255, Math.max(0, level + contrast * (0.6 * ridge + 0.8 * (rand() - 0.5))));
    }
  }
  return out;
}

/** A box blur, applied `passes` times: what an out-of-focus or far-away muzzle does to the texture. */
function blur(gray: Float32Array, passes: number): Float32Array {
  let src = gray;
  for (let pass = 0; pass < passes; pass++) {
    const dst = new Float32Array(src.length);
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        let sum = 0;
        let n = 0;
        for (let dy = -2; dy <= 2; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            const yy = y + dy;
            const xx = x + dx;
            if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
            sum += src[yy * W + xx]!;
            n++;
          }
        }
        dst[y * W + x] = sum / n;
      }
    }
    src = dst;
  }
  return src;
}

describe("scan quality (a capture hint, not identity confidence)", () => {
  it("scores a sharp textured muzzle as good and fills the meter", () => {
    const quality = scoreGray(texture(128, 120), W, H);
    expect(quality.status).toBe("good");
    expect(quality.sharpness).toBeGreaterThanOrEqual(SHARP_ENOUGH);
    expect(quality.score).toBeGreaterThan(0.8);
    expect(quality.motion).toBeNull();
  });

  it("scores the same muzzle blurred as soft, asking to move closer", () => {
    const sharp = scoreGray(texture(128, 120), W, H);
    const soft = scoreGray(blur(texture(128, 120), 3), W, H);
    expect(soft.laplacianVariance).toBeLessThan(sharp.laplacianVariance / 10);
    expect(soft.status).toBe("soft");
    expect(soft.score).toBeLessThan(sharp.score);
    expect(soft.score).toBeLessThan(SHARP_ENOUGH);
  });

  it("calls a dark frame too dark and a blown-out frame too bright, whatever its texture", () => {
    const dark = scoreGray(texture(22, 30), W, H);
    expect(dark.status).toBe("dark");
    expect(dark.brightness).toBeLessThan(50);
    expect(dark.score).toBe(0);
    const bright = scoreGray(texture(245, 16), W, H);
    expect(bright.status).toBe("bright");
    expect(bright.score).toBeLessThan(0.4);
    const lit = scoreGray(texture(140, 120), W, H);
    expect(lit.score).toBeGreaterThan(bright.score);
  });

  it("says the picture is moving when consecutive samples differ a lot, and steady when they don't", () => {
    const first = texture(128, 120, 1);
    const shaken = texture(128, 120, 2);
    expect(scoreGray(shaken, W, H, first).status).toBe("moving");
    const still = scoreGray(first, W, H, first);
    expect(still.motion).toBe(0);
    expect(still.status).toBe("good");
  });

  it("reads RGBA image data through the same scorer", () => {
    const gray = texture(128, 120);
    const rgba = new Uint8ClampedArray(W * H * 4);
    gray.forEach((value, i) => rgba.set([value, value, value, 255], i * 4));
    const { quality, gray: back } = scoreImage({ data: rgba, width: W, height: H });
    expect(meanOf(back)).toBeCloseTo(meanOf(toGray(rgba, W, H)), 5);
    expect(quality.status).toBe("good");
  });

  it("maps a flat image to zero sharpness and saturates at full detail", () => {
    expect(laplacianVariance(new Float32Array(W * H).fill(120), W, H)).toBe(0);
    expect(sharpnessFrom(0)).toBe(0);
    expect(sharpnessFrom(10_000)).toBe(1);
  });

  it("eases the meter toward the newest score but keeps the newest status", () => {
    const low = scoreGray(blur(texture(128, 120), 3), W, H);
    const high = scoreGray(texture(128, 120), W, H);
    const eased = smoothQuality(low, high);
    expect(eased.score).toBeGreaterThan(low.score);
    expect(eased.score).toBeLessThan(high.score);
    expect(eased.status).toBe("good");
  });
});
