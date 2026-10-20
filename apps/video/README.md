# VEYRA launch film (Remotion)

A 3:31 voiceover-synchronized product launch film for VEYRA in the "Product Launch Reveal" keynote style:
the team's real cattle footage, a rim-lit phone showing the app's Ear Tag UI, and the in-app VEYRA AI agent.
1280×720, 30 fps, deterministic (every frame is a pure function of the frame number, seeded randomness only).

```
pnpm install
pnpm dev                 # Remotion Studio (composition "VeyraLaunch")
pnpm render              # -> out/veyra-launch.mp4 (H.264 + AAC, mixed audio)
pnpm stills              # -> out/stills/{reveal,agent-insurance,tagline}.png
```

Rendering uses a local Chrome/Edge when it finds one (see `remotion.config.ts`, or set `BROWSER_EXECUTABLE`),
otherwise Remotion downloads its headless shell. A full render takes roughly 20–40 minutes on a laptop.

## How it is put together

| Path | What it is |
| --- | --- |
| `src/beats.ts` | **BEATS**: the timing table. One entry per idea (start, end, words, what is on screen, exact cue times). Every animation and every sound reads its times from here. |
| `src/words.json`, `src/script.json` | Word cues and sentences parsed from the brief (`pnpm words` → `scripts/gen-words.mjs`, reads `../../../VIDEO.md`). |
| `src/Film.tsx` | The composition: stage → scene backgrounds → hero phone → scene overlays → finishing (vignette + grain) → audio. |
| `src/phone-track.ts` | The hero phone's continuous camera (eased pose keys), its lighting (rim, key, specular sweeps, edge ring pulses). |
| `src/screens.tsx` | Which app screen the phone shows at each moment, and which capture/key moment would replace it. |
| `src/scenes/*` | One file per beat group: Problem, Reveal (+Herd), Enroll, Passport, Insurance, Approval, Monitor, Late (Ask, Claim, Audit, Close). |
| `src/components/*` | Stage (canvas port of the reference `stage()`), Finish (grain/vignette), Type (word reveal, callouts, gradient numbers, strikes), Phone, PhoneScreen, Footage, Cctv, Sweep. |
| `src/app-screens/*` | Ear Tag recreations of the app screens (Herd, Scan Cow, Review, Passport, VEYRA AI agent, Approvals, Monitor, Ask, Incident, Claim, Audit) and the seeded demo data. |
| `src/lib/h.ts` | Port of the brief's H helper library (rng, noise, easing, keyed cameras). |
| `src/audio/sound.js` | The brief's SOUND kit, verbatim. `src/audio/score.ts` is the film's score on that kit. |
| `public/footage/` | Copies of `demo/media/veo` (muted, short-GOP re-encodes, reversed copies for ping-pong) and stills. |
| `src/data/tracks.json` | The recorded CCTV track data; the film draws its own boxes from it (only track 11 is associated). |

Timing rule: a visual lands on its word (cues fire `LEAD = 0.1 s` before the word, never after). To retime for a
new take of the same script, regenerate `src/words.json` (`pnpm words`); the `at(sentence, "word")` lookups in
`beats.ts` pick up the new times automatically.

## Audio

Three stems in `public/audio/` (tracked with Git LFS):

* `voice.wav`: **temporary** text-to-speech voiceover (edge-tts, en-US-AndrewNeural). `pnpm voice` regenerates it
  (`scripts/make-voice.py`): each sentence is synthesized with word boundaries, cut into phrases, time-fitted
  with ffmpeg `atempo` (0.8–1.25) and placed so every phrase starts on its cue word.
* `effects.wav`: the score. `pnpm effects` bundles `src/audio/score.ts` and runs
  `SOUND.renderOffline(scoreSound, DURATION, 48000, { voiceover: true })` in a headless browser.
* `mix.wav`: `pnpm mix` (`scripts/mix.mjs`) runs the brief's ffmpeg chain: voice loudnorm −17, effects −26,
  effects sidechain-compressed under the voice, summed and normalized to −16 LUFS.

The film plays `mix.wav` (or `voice.wav` if there is no mix).

### Replacing the TTS voice with a real recording

1. Record the script as written (`src/script.json`, or the brief's word cues) so the words fall on the cue times.
   If the new take's timing differs, update the word cues in `VIDEO.md` (or write `src/words.json` directly from a
   forced alignment) and run `pnpm words`.
2. Save it as `public/audio/voice.wav` (48 kHz WAV, mono or stereo), replacing the TTS file.
3. `pnpm audio` (re-renders the effects on the new BEATS and re-mixes), then `pnpm render`.

## Swapping in real footage or app captures

* **Footage**: replace the files in `public/footage/` with the same names (`hp.mp4` phone enrollment take, `cctv.mp4`
  barn camera, plus their `_rev` reversed copies:
  `ffmpeg -i in.mp4 -vf reverse -an -c:v libx264 -crf 18 -g 6 out_rev.mp4`). Cut points live in
  `src/footage-plan.ts` and the scene files (`segments`: film start/end, source offset, rate).
* **App captures**: put 390×844 (@2x) phone-viewport recordings in `public/app/` with a `captures.json` manifest,
  e.g. `{ "herd": { "mp4": "herd.mp4", "png": "herd.png", "moments": { "herd": 0.5 } } }`.
  `<PhoneScreen>` reads it at render time: each screen state in `src/screens.tsx` names a capture and a key
  moment; when that capture exists it plays from that moment, otherwise the recreation renders. The VEYRA AI
  agent states map to `agent-insurance` (moments `proactive`, `application`) and `agent-claim` (`request`).

## Notes

* No subtitles; on-screen text is headlines, labels, values and states only (headlines ≥ 44 px, story labels
  ≥ 28 px, key numbers ≥ 64 px). The phone UI itself is smaller, as on a real phone; anything the story depends on
  is repeated outside the phone at full size.
* All insurance activity is sandboxed and shown as such; no payout is ever shown as done.
