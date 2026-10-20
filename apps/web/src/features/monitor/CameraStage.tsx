import { TriangleAlert, VideoOff } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { EarTag } from "../../components/EarTag";
import { cn } from "../../lib/cn";
import type { Replay, Scenario, ScenarioTrack, Track } from "./api";
import { boxAt, matchFlashing, type TrackEvent } from "./interpolate";
import { identityAt, type TrackIdentity } from "./track-state";
import type { ReplayClock } from "./use-replay-clock";

/** The match flash lasts at most 200ms of real time. */
const FLASH_MS = 200;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function identityKey(id: TrackIdentity): string {
  return id.status === "unassigned" ? "u" : `${id.status}:${id.animalId ?? ""}`;
}

function TrackLabel({ identity, trackKey, selected }: { identity: TrackIdentity; trackKey: string; selected: boolean }) {
  if (identity.status === "associated") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-2 rounded-control bg-bg py-0.5 pr-2.5 pl-1 font-bold whitespace-nowrap text-ink shadow-raised",
          selected && "outline-3 outline-tag",
        )}
      >
        <EarTag animalId={identity.animalId} state="confirmed" size="sm" className="h-8" />
        {identity.name}
      </span>
    );
  }
  if (identity.status === "uncertain") {
    return (
      <span className="inline-flex min-h-9 items-center gap-1.5 rounded-control bg-uncertain-soft px-2.5 text-sm font-bold whitespace-nowrap text-uncertain-ink shadow-raised">
        <TriangleAlert aria-hidden="true" className="size-4" strokeWidth={2.5} />
        Identity uncertain
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-control bg-surface-2 py-0.5 pr-2.5 pl-1 text-sm font-bold whitespace-nowrap text-muted shadow-raised">
      <EarTag state="none" size="sm" className="h-8" />
      <span className="figures">{trackKey}</span>
    </span>
  );
}

export interface CameraStageProps {
  scenario: Scenario | undefined;
  replay: Replay | undefined;
  clock: ReplayClock;
  selectedAnimalId: string | null;
  cameraName: string | null;
}

/**
 * The 16:9 camera stage. With a clip it plays the video; without one it is a neutral stage that says so. A
 * canvas draws every track's box at the replay clock's time, and DOM chips carry each track's identity.
 */
export function CameraStage({ scenario, replay, clock, selectedAnimalId, cameraName }: CameraStageProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const labelRefs = useRef(new Map<string, HTMLDivElement>());
  const reduced = usePrefersReducedMotion();
  const [identities, setIdentities] = useState<Record<string, TrackIdentity>>({});
  const identitiesRef = useRef<Record<string, string>>({});
  const active = Boolean(replay && scenario);
  const now = clock.now;

  const tracks = useMemo(() => {
    if (!scenario || !replay) return [];
    const server = new Map<string, Track>(replay.tracks.map((t) => [t.track_key, t]));
    return scenario.tracks.map((st: ScenarioTrack) => ({
      key: st.track_key,
      scenario: st,
      server: server.get(st.track_key),
      events: st.events as TrackEvent[],
    }));
  }, [scenario, replay]);

  // Draw loop: boxes on the canvas, label chips moved directly, identity changes pushed to React.
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const colors = {
      tag: cssVar("--tag", "#f2c400"),
      uncertain: cssVar("--uncertain", "#c2410c"),
      grey: cssVar("--line-strong", "#8a8f98"),
      grid: "rgba(255,255,255,0.06)",
      white: "#ffffff",
    };
    let frame = 0;
    let width = 0;
    let height = 0;
    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    observer?.observe(wrap);

    const draw = () => {
      const t = now();
      ctx.clearRect(0, 0, width, height);
      // A faint floor grid so motion reads even without footage.
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;
      for (let i = 1; i < 8; i++) {
        ctx.beginPath();
        ctx.moveTo((width * i) / 8, 0);
        ctx.lineTo((width * i) / 8, height);
        ctx.stroke();
      }
      for (let i = 1; i < 5; i++) {
        ctx.beginPath();
        ctx.moveTo(0, (height * i) / 5);
        ctx.lineTo(width, (height * i) / 5);
        ctx.stroke();
      }
      const flashS = replay ? (FLASH_MS / 1000) * Math.max(1, replay.speed) : 0;
      const changed: Record<string, TrackIdentity> = {};
      let dirty = false;
      for (const track of tracks) {
        const box = active ? boxAt(track.scenario.frames, t, track.events) : null;
        const label = labelRefs.current.get(track.key);
        const identity = identityAt(track.scenario, track.server, t);
        const key = identityKey(identity);
        if (identitiesRef.current[track.key] !== key) {
          identitiesRef.current[track.key] = key;
          changed[track.key] = identity;
          dirty = true;
        }
        if (!box) {
          if (label) label.style.visibility = "hidden";
          continue;
        }
        const [bx, by, bw, bh] = box;
        const x = bx * width;
        const y = by * height;
        const w = bw * width;
        const h = bh * height;
        const selected = identity.status !== "unassigned" && identity.animalId === selectedAnimalId && selectedAnimalId !== null;
        ctx.setLineDash(identity.status === "unassigned" ? [6, 5] : []);
        ctx.lineWidth = selected ? 4 : 2.5;
        ctx.strokeStyle =
          identity.status === "associated" ? colors.tag : identity.status === "uncertain" ? colors.uncertain : colors.grey;
        ctx.strokeRect(x, y, w, h);
        if (selected) {
          ctx.setLineDash([]);
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = colors.white;
          ctx.strokeRect(x - 4, y - 4, w + 8, h + 8);
        }
        // Muzzle-match moment: one brief outline, skipped under reduced motion.
        if (!reduced && flashS > 0 && matchFlashing(track.events, t, flashS)) {
          const since = t - (track.events.find((e) => e.type === "muzzle_match")?.t ?? t);
          const k = 1 - since / flashS;
          ctx.setLineDash([]);
          ctx.lineWidth = 3;
          ctx.strokeStyle = `rgba(255,255,255,${(0.9 * k).toFixed(3)})`;
          const grow = 10 * (1 - k);
          ctx.strokeRect(x - 6 - grow, y - 6 - grow, w + 12 + grow * 2, h + 12 + grow * 2);
        }
        if (label) {
          label.style.visibility = "visible";
          const above = y - 46;
          label.style.transform = `translate(${Math.max(4, Math.min(x, width - label.offsetWidth - 4))}px, ${above < 4 ? y + 6 : above}px)`;
        }
      }
      ctx.setLineDash([]);
      if (dirty) setIdentities((prev) => ({ ...prev, ...changed }));
      frame = window.requestAnimationFrame(draw);
    };
    frame = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [tracks, now, selectedAnimalId, reduced, active, replay]);

  // Keep a clip, when there is one, on the replay clock.
  const clip = scenario?.clip ?? null;
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !clip) return;
    if (Number.isFinite(video.duration) && Math.abs(video.currentTime - clock.t) > 0.6) {
      video.currentTime = Math.min(clock.t, video.duration || clock.t);
    }
  }, [clip, clock.t]);

  return (
    <div
      ref={wrapRef}
      className="relative aspect-video w-full overflow-hidden rounded-panel bg-shell text-on-shell"
      role="img"
      aria-label={
        active
          ? `Camera ${cameraName ?? ""}: ${tracks.length} tracks drawn from recorded track data`
          : `Camera ${cameraName ?? ""}: no replay running`
      }
    >
      {clip && <video ref={videoRef} src={clip} muted playsInline preload="auto" className="absolute inset-0 size-full object-cover" />}
      <canvas ref={canvasRef} className="absolute inset-0 size-full" aria-hidden="true" />
      {tracks.map((track) => {
        const identity = identities[track.key] ?? { status: "unassigned" as const };
        const selected = identity.status !== "unassigned" && identity.animalId === selectedAnimalId;
        return (
          <div
            key={track.key}
            ref={(el) => {
              if (el) labelRefs.current.set(track.key, el);
              else labelRefs.current.delete(track.key);
            }}
            className="pointer-events-none absolute top-0 left-0"
            style={{ visibility: "hidden" }}
            aria-hidden="true"
          >
            <TrackLabel identity={identity} trackKey={track.key} selected={selected} />
          </div>
        );
      })}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-2 p-3">
        <span className="rounded-control bg-shell/85 px-2.5 py-1 text-sm font-bold">{cameraName ?? "Camera"}</span>
        {!clip && (
          <span className="inline-flex items-center gap-1.5 rounded-control bg-shell/85 px-2.5 py-1 text-sm text-on-shell-muted">
            <VideoOff aria-hidden="true" className="size-4" strokeWidth={2.25} />
            No footage attached · track data only (simulated)
          </span>
        )}
      </div>
      {!active && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
          <p className="text-md font-bold">No replay on this camera yet</p>
          <p className="max-w-[44ch] text-on-shell-muted">
            Pick a recorded scenario and start the replay. Each track is drawn here as it is observed.
          </p>
        </div>
      )}
    </div>
  );
}
