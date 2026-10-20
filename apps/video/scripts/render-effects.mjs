// Render the sound-effects stem: public/audio/effects.wav (48 kHz stereo, 16-bit).
//   node scripts/render-effects.mjs [--browser "C:/path/to/chrome-or-edge.exe"]
// Bundles src/audio/score.ts (which reads the BEATS table) with esbuild, loads it next to the brief's SOUND kit
// (src/audio/sound.js) in a headless browser and runs
//   SOUND.renderOffline(scoreSound, DURATION, 48000, { voiceover: true })
// then writes the interleaved floats to a WAV file.
import { build } from "esbuild";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (k) => {
  const i = process.argv.indexOf(k);
  return i > 0 ? process.argv[i + 1] : undefined;
};
const CANDIDATES = [
  arg("--browser"),
  process.env.BROWSER_EXECUTABLE,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const executablePath = CANDIDATES.find((p) => existsSync(p));
if (!executablePath) throw new Error("No Chrome/Edge found; pass --browser <path>");

const bundle = await build({
  entryPoints: [resolve(root, "src/audio/score-entry.ts")],
  bundle: true,
  write: false,
  format: "iife",
  platform: "browser",
  target: "es2020",
  logLevel: "error",
});
const scoreJs = bundle.outputFiles[0].text;
const soundJs = readFileSync(resolve(root, "src/audio/sound.js"), "utf8");

const browser = await puppeteer.launch({ executablePath, headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
try {
  const page = await browser.newPage();
  await page.setContent("<!doctype html><html><body></body></html>");
  await page.addScriptTag({ content: soundJs });
  await page.addScriptTag({ content: scoreJs });
  const info = await page.evaluate(async () => {
    const sr = 48000;
    const r = await window.SOUND.renderOffline(window.scoreSound, window.DURATION, sr, { voiceover: true });
    const scale = r.peak > 0.98 ? 0.98 / r.peak : 1;
    const pcm = new Int16Array(r.inter.length);
    for (let i = 0; i < r.inter.length; i++) pcm[i] = Math.max(-32768, Math.min(32767, Math.round(r.inter[i] * scale * 32767)));
    window.__pcm = pcm;
    return { frames: r.frames, peak: r.peak, scale, samples: pcm.length };
  });
  // pull the PCM out in chunks (base64)
  const CHUNK = 1 << 21;
  const parts = [];
  for (let off = 0; off < info.samples; off += CHUNK) {
    const b64 = await page.evaluate(
      (o, n) => {
        const a = window.__pcm.subarray(o, Math.min(window.__pcm.length, o + n));
        const u8 = new Uint8Array(a.buffer, a.byteOffset, a.byteLength);
        let s = "";
        for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
        return btoa(s);
      },
      off,
      CHUNK,
    );
    parts.push(Buffer.from(b64, "base64"));
  }
  const data = Buffer.concat(parts);
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(2, 22); // stereo
  header.writeUInt32LE(48000, 24);
  header.writeUInt32LE(48000 * 4, 28);
  header.writeUInt16LE(4, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  mkdirSync(resolve(root, "public/audio"), { recursive: true });
  const out = resolve(root, "public/audio/effects.wav");
  writeFileSync(out, Buffer.concat([header, data]));
  console.log(`wrote ${out}: ${(info.frames / 48000).toFixed(2)} s, peak ${info.peak.toFixed(3)}${info.scale < 1 ? ` (scaled x${info.scale.toFixed(3)})` : ""}`);
} finally {
  await browser.close();
}
