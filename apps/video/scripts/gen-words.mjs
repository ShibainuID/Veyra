// Parse the word-level voiceover cues (SRT-style) out of the brief into src/words.json and src/script.json.
//   node scripts/gen-words.mjs [path/to/VIDEO.md]
// words.json:  [{ i, w, s, e }]  (index, word as spoken, start/end in seconds)
// script.json: [{ i, text, s, e, w0, w1 }]  sentences (split after . ? !), with their first/last word index.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(process.argv[2] ?? resolve(here, "../../../../VIDEO.md"));
const text = readFileSync(src, "utf8").replace(/\r\n/g, "\n");

const start = text.indexOf("MY VOICEOVER TIMING:");
const end = text.indexOf("\nWHAT TO BUILD");
if (start < 0 || end < 0) throw new Error("Could not find the voiceover timing block in " + src);
const block = text.slice(start, end);

const ts = (s) => {
  const m = /(\d+):(\d+):(\d+),(\d+)/.exec(s);
  return +m[1] * 3600 + +m[2] * 60 + +m[3] + +m[4] / 1000;
};
const cue = /^(\d+)\n(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)\n(.+)$/gm;
const words = [];
for (const m of block.matchAll(cue)) {
  words.push({ i: words.length, w: m[4].trim(), s: +ts(m[2]).toFixed(3), e: +ts(m[3]).toFixed(3) });
}
if (!words.length) throw new Error("No cues parsed");

const sentences = [];
let cur = [];
for (const w of words) {
  cur.push(w);
  if (/[.?!]["”’)]?$/.test(w.w)) {
    sentences.push(cur);
    cur = [];
  }
}
if (cur.length) sentences.push(cur);
const script = sentences.map((ws, i) => ({
  i,
  text: ws.map((w) => w.w).join(" "),
  s: ws[0].s,
  e: ws[ws.length - 1].e,
  w0: ws[0].i,
  w1: ws[ws.length - 1].i,
}));

writeFileSync(resolve(here, "../src/words.json"), JSON.stringify(words) + "\n");
writeFileSync(resolve(here, "../src/script.json"), JSON.stringify(script, null, 1) + "\n");
console.log(`${words.length} words, ${script.length} sentences, last word ends ${words.at(-1).e}s`);
