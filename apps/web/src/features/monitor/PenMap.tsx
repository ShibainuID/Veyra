import { EarTag } from "../../components/EarTag";
import { Timestamp } from "../../components/figures";
import { cn } from "../../lib/cn";
import type { AnimalListItem, Camera } from "./api";
import { FIELD_OF_VIEW, toMapPoint, type Box } from "./interpolate";

/** Map units: the SVG is drawn in a 1000 × 420 box; cameras and animals sit at normalized map_x / map_y. */
const W = 1000;
const H = 420;

export interface LivePosition {
  key: string;
  cameraId: string;
  box: Box;
  animalId: string | null;
  trackKey: string;
}

export interface PenMapProps {
  cameras: readonly Camera[];
  animals: readonly AnimalListItem[];
  /** Tracks drawn on the stage right now, placed through the same camera coordinates. */
  live: readonly LivePosition[];
  selectedAnimalId: string | null;
  activeCameraId: string | null;
  onSelect: (animalId: string) => void;
}

interface Marker {
  key: string;
  x: number;
  y: number;
  animalId: string | null;
  name: string;
  state: "confirmed" | "pending" | "none";
  trackKey?: string;
  live: boolean;
}

function clamp01(v: number) {
  return Math.max(0.03, Math.min(0.97, v));
}

/**
 * The pen map shares one coordinate space with the camera stage and the herd: a camera's field of view is a
 * box around its map position, a track's box centre lands inside it, and an animal with no live track sits by
 * the camera that last saw it. Picking an animal anywhere highlights where it was last seen.
 */
export function PenMap({ cameras, animals, live, selectedAnimalId, activeCameraId, onSelect }: PenMapProps) {
  const camerasById = new Map(cameras.map((c) => [c.id, c]));
  const liveAnimals = new Set(live.map((p) => p.animalId).filter(Boolean));
  const markers: Marker[] = [];

  for (const position of live) {
    const camera = camerasById.get(position.cameraId);
    if (!camera) continue;
    const point = toMapPoint(camera, position.box);
    const animal = position.animalId ? animals.find((a) => a.id === position.animalId) : undefined;
    markers.push({
      key: `live-${position.key}`,
      x: clamp01(point.x),
      y: clamp01(point.y),
      animalId: position.animalId,
      name: animal?.name ?? (position.animalId ? position.animalId : `Track ${position.trackKey}`),
      state: position.animalId ? (animal?.identity_status === "pending_review" ? "pending" : "confirmed") : "none",
      trackKey: position.trackKey,
      live: true,
    });
  }

  const resting = animals.filter((a) => a.last_observation && !liveAnimals.has(a.id));
  const byCamera = new Map<string, AnimalListItem[]>();
  for (const animal of resting) {
    const id = animal.last_observation!.camera_id;
    byCamera.set(id, [...(byCamera.get(id) ?? []), animal]);
  }
  for (const [cameraId, group] of byCamera) {
    const camera = camerasById.get(cameraId);
    if (!camera) continue;
    group.forEach((animal, i) => {
      markers.push({
        key: `rest-${animal.id}`,
        x: clamp01(camera.map_x + (i - (group.length - 1) / 2) * 0.065),
        y: clamp01(camera.map_y + FIELD_OF_VIEW.height / 2 - 0.1),
        animalId: animal.id,
        name: animal.name,
        state: animal.identity_status === "pending_review" ? "pending" : "confirmed",
        live: false,
      });
    });
  }

  const selected = selectedAnimalId ? animals.find((a) => a.id === selectedAnimalId) : undefined;
  const selectedLive = live.find((p) => p.animalId === selectedAnimalId);
  const lastCameraId = selectedLive?.cameraId ?? selected?.last_observation?.camera_id ?? null;

  return (
    <figure className="flex flex-col gap-3">
      {/* Below ~640px the map keeps a legible scale and scrolls sideways inside its frame instead of shrinking. */}
      <div role="region" aria-label="Pen map" tabIndex={0} className="overflow-x-auto rounded-panel border-2 border-line bg-surface">
      <div className="relative w-full min-w-[640px] overflow-hidden" style={{ aspectRatio: `${W} / ${H}` }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 size-full" aria-hidden="true">
          {cameras.map((camera) => {
            const cx = camera.map_x * W;
            const cy = camera.map_y * H;
            const fw = FIELD_OF_VIEW.width * W;
            const fh = FIELD_OF_VIEW.height * H;
            const isLast = camera.id === lastCameraId;
            const isActive = camera.id === activeCameraId;
            return (
              <g key={camera.id}>
                <rect
                  x={cx - fw / 2}
                  y={cy - fh / 2}
                  width={fw}
                  height={fh}
                  rx={12}
                  fill={isLast ? "var(--tag-soft)" : "var(--bg)"}
                  stroke={isLast ? "var(--ink)" : isActive ? "var(--line-strong)" : "var(--line)"}
                  strokeWidth={isLast ? 4 : 2}
                  strokeDasharray={isLast || isActive ? undefined : "8 6"}
                />
                {/* The camera hangs on the pen's top edge, looking in. */}
                <rect x={cx - 13} y={cy - fh / 2 - 11} width={26} height={22} rx={5} fill="var(--ink)" />
                <circle cx={cx} cy={cy - fh / 2} r={5} fill="var(--tag)" />
                <text
                  x={cx - fw / 2 + 4}
                  y={cy - fh / 2 - 12}
                  fontSize={22}
                  fontWeight={700}
                  fill="var(--ink)"
                  fontFamily="var(--font-sans)"
                >
                  {camera.location}
                </text>
              </g>
            );
          })}
        </svg>
        {markers.map((m) => {
          const isSelected = m.animalId !== null && m.animalId === selectedAnimalId;
          const label = m.animalId
            ? `${m.name}, ${m.live ? "on camera now" : "last seen here"}${isSelected ? ", selected" : ""}`
            : `Unassigned track ${m.trackKey}`;
          return (
            <button
              key={m.key}
              type="button"
              aria-label={label}
              aria-pressed={m.animalId ? isSelected : undefined}
              disabled={!m.animalId}
              onClick={() => m.animalId && onSelect(m.animalId)}
              className={cn(
                "absolute grid min-h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-control",
                "transition-[left,top] duration-(--dur-base) ease-out-quart disabled:cursor-default",
                isSelected && "z-10 bg-ink/90 ring-4 ring-ink",
              )}
              style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%` }}
            >
              <EarTag
                animalId={m.animalId ?? undefined}
                state={m.state}
                size="sm"
                className={cn("h-7 md:h-9", m.live && "drop-shadow-sm")}
              />
            </button>
          );
        })}
      </div>
      </div>
      <figcaption className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-muted">
        {selected ? (
          selectedLive ? (
            <span>
              <strong className="text-ink">{selected.name}</strong> is on{" "}
              {camerasById.get(selectedLive.cameraId)?.name ?? selectedLive.cameraId} in this replay.
            </span>
          ) : selected.last_observation ? (
            <span>
              <strong className="text-ink">{selected.name}</strong> was last seen on{" "}
              {selected.last_observation.camera_name ?? selected.last_observation.camera_id},{" "}
              <Timestamp value={selected.last_observation.observed_at} className="text-ink" />. This is a past observation,
              not a live location.
            </span>
          ) : (
            <span className="font-bold text-uncertain-ink">No camera observation is on record for {selected.name}.</span>
          )
        ) : (
          <span>Each tag sits by the camera that last saw it. Pick one to see where.</span>
        )}
      </figcaption>
    </figure>
  );
}
