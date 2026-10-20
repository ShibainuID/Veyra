// Mix the voiceover over the effects with the brief's chain (effects ducked under the voice), keep the stems:
//   public/audio/voice.wav + public/audio/effects.wav -> public/audio/mix.wav (48 kHz stereo)
//   node scripts/mix.mjs
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const a = (p) => resolve(root, "public/audio", p);
for (const f of ["voice.wav", "effects.wav"]) if (!existsSync(a(f))) throw new Error(`missing public/audio/${f}`);

// The brief's filter graph (same loudness targets, sidechain and mix), writing a WAV stem instead of muxing into
// an MP4 here. Each loudnorm is followed by aresample/aformat (loudnorm runs at 192 kHz internally).
const graph =
  "[0:a]loudnorm=I=-17:TP=-2,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=2[v1][v2];" +
  "[1:a]loudnorm=I=-26:TP=-4:LRA=20,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[fx0];" +
  "[fx0][v1]sidechaincompress=threshold=0.05:ratio=3:attack=10:release=250[fx];" +
  "[v2][fx]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]";
const run = (g) =>
  execFileSync(
    "ffmpeg",
    ["-v", "error", "-y", "-i", a("voice.wav"), "-i", a("effects.wav"), "-filter_complex", g, "-map", "[a]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", "-t", "211", a("mix.wav")],
    { stdio: "pipe" },
  );
try {
  run(graph);
} catch {
  // ffmpeg < 4.4 has no amix normalize option: amix divides by the input count, so undo that with volume=2
  run(graph.replace("amix=inputs=2:normalize=0", "amix=inputs=2,volume=2"));
}
console.log("wrote", a("mix.wav"));
