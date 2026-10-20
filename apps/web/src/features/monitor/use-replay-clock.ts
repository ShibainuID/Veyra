import { useCallback, useEffect, useRef, useState } from "react";
import type { Replay } from "./api";
import { replayTimeAt, type ClockSample } from "./interpolate";

/** Local playback after a replay settles: the recorded track data played back at this rate. */
export const LOCAL_RATE = 10;

export interface ReplayClock {
  /** Read every animation frame (no re-render). */
  now: () => number;
  /** The same time, updated a few times a second for readouts. */
  t: number;
  /** "live" while the server replay runs; "local" once the operator scrubs or plays back. */
  mode: "idle" | "live" | "local";
  playing: boolean;
  /** Local playback speed: simulated seconds per real second. */
  rate: number;
  play: () => void;
  pause: () => void;
  seek: (t: number) => void;
}

/**
 * The overlay's clock. While the replay runs, it follows the server's reported progress (`progress_s`) and runs
 * on at the replay speed between polls, never ahead of what was reported by more than a few seconds and never
 * backwards. When the replay is over, the operator can scrub or play the recorded tracks back locally.
 */
export function useReplayClock(replay: Replay | undefined, durationS: number, rate: number = LOCAL_RATE): ReplayClock {
  const sampleRef = useRef<ClockSample | null>(null);
  const shownRef = useRef(0);
  const localRef = useRef<{ base: number; at: number; playing: boolean } | null>(null);
  const [t, setT] = useState(0);
  const [mode, setMode] = useState<ReplayClock["mode"]>("idle");
  const [playing, setPlaying] = useState(false);
  const replayId = replay?.id;

  // A new replay starts the clock from its own progress.
  useEffect(() => {
    shownRef.current = 0;
    localRef.current = null;
    setPlaying(false);
  }, [replayId]);

  useEffect(() => {
    if (!replay) {
      sampleRef.current = null;
      setMode("idle");
      return;
    }
    sampleRef.current = {
      progressS: replay.progress_s,
      receivedAt: Date.now(),
      speed: replay.speed,
      durationS: replay.duration_s || durationS,
      status: replay.status,
    };
    if (localRef.current === null) setMode(replay.status === "running" ? "live" : "local");
  }, [replay, durationS]);

  const now = useCallback(() => {
    const local = localRef.current;
    if (local) {
      const value = local.playing ? local.base + ((Date.now() - local.at) / 1000) * rate : local.base;
      if (value >= durationS && local.playing) {
        localRef.current = { base: durationS, at: Date.now(), playing: false };
        setPlaying(false);
        return durationS;
      }
      return Math.min(durationS, value);
    }
    const sample = sampleRef.current;
    if (!sample) return 0;
    const value = Math.max(shownRef.current, replayTimeAt(sample, Date.now()));
    shownRef.current = value;
    return value;
  }, [durationS, rate]);

  useEffect(() => {
    const id = window.setInterval(() => setT(now()), 250);
    return () => window.clearInterval(id);
  }, [now]);

  const seek = useCallback(
    (value: number) => {
      const clamped = Math.max(0, Math.min(durationS, value));
      localRef.current = { base: clamped, at: Date.now(), playing: localRef.current?.playing ?? false };
      setMode("local");
      setT(clamped);
    },
    [durationS],
  );

  const play = useCallback(() => {
    const current = localRef.current ? now() : sampleRef.current?.status === "running" ? now() : 0;
    const start = current >= durationS - 0.5 ? 0 : current;
    localRef.current = { base: start, at: Date.now(), playing: true };
    setMode("local");
    setPlaying(true);
  }, [durationS, now]);

  const pause = useCallback(() => {
    const value = now();
    localRef.current = { base: value, at: Date.now(), playing: false };
    setPlaying(false);
    setT(value);
  }, [now]);

  return { now, t, mode, playing, rate, play, pause, seek };
}
