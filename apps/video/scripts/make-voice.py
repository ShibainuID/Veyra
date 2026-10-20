"""Regenerate the TEMPORARY text-to-speech voiceover: public/audio/voice.wav (48 kHz, mono, 16-bit).

    uv run --with edge-tts==7.2.3 python scripts/make-voice.py [--voice en-US-AndrewNeural] [--force]

Each sentence of src/script.json (built from the brief's word cues by scripts/gen-words.mjs) is synthesized with
edge-tts, which also reports where every word starts in the take. The take is then cut into phrases (at commas,
colons and pauses in the cue timing) and each phrase is time-fitted with ffmpeg `atempo` (0.8-1.25) so that it
starts on its first word's cue time and ends by the next phrase's cue (or the sentence's last word end). If a take
is too long overall it is first re-synthesized at a faster speaking rate, which sounds better than heavy stretching.
A phrase that is still too long after the 1.25 limit is trimmed with a short fade; one that is too short leaves a
pause. Every fitted phrase is placed at its cue time in one track.

To use a real recording instead, replace public/audio/voice.wav with a file of the same name whose words follow
the same timing (see README.md), then run `pnpm mix`.
"""

from __future__ import annotations

import argparse
import array
import asyncio
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache" / "voice"
OUT = ROOT / "public" / "audio" / "voice.wav"
SR = 48000
TAIL = 211.0  # composition length in seconds (last word end + ~1 s)
LEAD = 0.03  # start each phrase this much before its cue word (consonant onsets)
TMIN, TMAX = 0.8, 1.25


def say(text: str) -> str:
    # Pronounce the brand as a word, not spelled-out capitals; use curly quotes for the quoted question.
    return text.replace("VEYRA", "Veyra").replace("'Where", "“Where").replace("seen?'", "seen?”")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


async def synth(text: str, voice: str, rate: int, mp3: Path, meta: Path) -> None:
    import edge_tts  # type: ignore

    for attempt in range(8):
        try:
            comm = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary="WordBoundary")
            audio = bytearray()
            marks = []
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    audio.extend(ch["data"])
                elif ch["type"] == "WordBoundary":
                    marks.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
            if not audio or not marks:
                raise RuntimeError("empty take")
            mp3.write_bytes(bytes(audio))
            meta.write_text(json.dumps(marks), encoding="utf8")
            return
        except Exception as err:  # the free endpoint rate-limits (429); back off and retry
            wait = 4 * 2**attempt
            print(f"  tts retry in {wait}s ({err.__class__.__name__}: {str(err)[:60]})", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"edge-tts failed for: {text[:60]}")


def decode(mp3: Path, wav: Path) -> array.array:
    ffmpeg("-i", str(mp3), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(wav))
    return read_pcm(wav)


def read_pcm(path: Path) -> array.array:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2
        data = array.array("h")
        data.frombytes(w.readframes(w.getnframes()))
        return data


def write_pcm(path: Path, pcm: array.array) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def align(cue_words: list[dict], marks: list[dict]) -> list[float]:
    """For every cue word, the take time where it starts (by matching normalized character offsets)."""
    pos, starts = 0, []
    for m in marks:
        starts.append((pos, m["t"]))
        pos += len(norm(m["w"]))
    out, pos = [], 0
    j = 0
    for w in cue_words:
        while j + 1 < len(starts) and starts[j + 1][0] <= pos:
            j += 1
        out.append(starts[j][1] if starts else 0.0)
        pos += len(norm(w["w"]))
    return out


def phrases(cue_words: list[dict]) -> list[tuple[int, int]]:
    """Split a sentence's words into phrases at punctuation or at gaps in the cue timing."""
    groups, a = [], 0
    for k in range(len(cue_words) - 1):
        w, nxt = cue_words[k], cue_words[k + 1]
        if re.search(r"[,;:]['’”]?$", w["w"]) or nxt["s"] - w["e"] > 0.15:
            groups.append((a, k))
            a = k + 1
    groups.append((a, len(cue_words) - 1))
    return groups


def atempo_chain(factor: float) -> str:
    return f"atempo={factor:.5f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en-US-AndrewNeural")
    ap.add_argument("--force", action="store_true", help="re-synthesize even if cached")
    a = ap.parse_args()

    words = json.loads((ROOT / "src" / "words.json").read_text(encoding="utf8"))
    script = json.loads((ROOT / "src" / "script.json").read_text(encoding="utf8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    track = array.array("h", bytes(2 * int(TAIL * SR)))
    report = []

    for sent in script:
        i, text = sent["i"], say(sent["text"])
        cw = words[sent["w0"] : sent["w1"] + 1]
        window = sent["e"] - sent["s"]
        rate = 0
        for attempt in range(4):
            stem = CACHE / f"{i:02d}_{a.voice}_{rate:+d}"
            mp3, meta = stem.with_suffix(".mp3"), stem.with_suffix(".json")
            if a.force or not (mp3.exists() and meta.exists()):
                asyncio.run(synth(text, a.voice, rate, mp3, meta))
            marks = json.loads(meta.read_text(encoding="utf8"))
            span = marks[-1]["t"] + marks[-1]["d"] - marks[0]["t"]
            ratio = span / window
            if 0.86 <= ratio <= 1.08 or attempt == 3:
                break
            if ratio > 1.08:  # too long: speak faster at the source
                rate = min(60, rate + max(4, round((ratio - 1.0) * 100) + 2))
            else:  # much shorter than the original read: speak a little slower (keynote pace)
                new = max(-25, rate - max(4, round((0.95 - ratio) * 100)))
                if new == rate:
                    break
                rate = new

        take = decode(mp3, stem.with_suffix(".wav"))
        src_t = align(cw, marks)
        last_end = marks[-1]["t"] + marks[-1]["d"]
        tempos = []
        groups = phrases(cw)
        for g, (p0, p1) in enumerate(groups):
            s0 = max(0.0, src_t[p0] - LEAD)
            s1 = (src_t[groups[g + 1][0]] - LEAD) if g + 1 < len(groups) else min(len(take) / SR, last_end + 0.12)
            d0 = cw[p0]["s"] - LEAD
            d1 = (cw[groups[g + 1][0]]["s"] - LEAD) if g + 1 < len(groups) else cw[-1]["e"] + 0.12
            src_len, dst_len = max(0.05, s1 - s0), max(0.05, d1 - d0)
            tempo = min(TMAX, max(TMIN, src_len / dst_len))
            seg = take[int(s0 * SR) : int(s1 * SR)]
            raw, fit = CACHE / "_seg.wav", CACHE / "_fit.wav"
            write_pcm(raw, seg)
            ffmpeg("-i", str(raw), "-af", atempo_chain(tempo), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(fit))
            pcm = read_pcm(fit)
            n_max = int(dst_len * SR)
            if len(pcm) > n_max:
                pcm = pcm[:n_max]
                for k in range(min(720, len(pcm))):
                    idx = len(pcm) - 1 - k
                    pcm[idx] = int(pcm[idx] * k / 720)
            off = int(round(d0 * SR))
            # mix (phrases never overlap, but the fade tails may touch)
            for k in range(len(pcm)):
                v = track[off + k] + pcm[k]
                track[off + k] = 32767 if v > 32767 else -32768 if v < -32768 else v
            tempos.append(tempo)
        report.append((i, window, ratio, rate, len(groups), min(tempos), max(tempos)))

    write_pcm(OUT, track)
    for i, window, ratio, rate, n, lo, hi in report:
        print(f"#{i:02d} window {window:5.2f}s  speech/window {ratio:4.2f}  rate {rate:+3d}%  phrases {n}  atempo {lo:.2f}-{hi:.2f}")
    print(f"wrote {OUT} ({TAIL:.0f} s, {SR} Hz mono)")


if __name__ == "__main__":
    sys.exit(main())
