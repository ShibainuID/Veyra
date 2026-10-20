import { CircleCheck, TriangleAlert } from "lucide-react";
import { useEffect, useId, useState, type RefObject } from "react";
import { Mono } from "../../components/figures";
import { cn } from "../../lib/cn";
import { muzzleGuideBox } from "./guide-box";
import { SAMPLE_WIDTH, STATUS_COPY, scoreImage, smoothQuality, type ScanQuality } from "./scan-quality";

const SAMPLE_EVERY_MS = 250;

function sampler() {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  return { canvas, context };
}

/**
 * Samples the live preview inside the muzzle guide box every 250 ms into a small canvas and scores it
 * (`scan-quality.ts`). Returns null until the first frame is scored, or while `enabled` is false.
 */
export function useLiveScanQuality(videoRef: RefObject<HTMLVideoElement | null>, enabled: boolean): ScanQuality | null {
  const [quality, setQuality] = useState<ScanQuality | null>(null);
  useEffect(() => {
    if (!enabled) {
      setQuality(null);
      return;
    }
    const { canvas, context } = sampler();
    if (!context) return;
    let previous: Float32Array | null = null;
    const id = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return;
      const box = muzzleGuideBox(video.videoWidth, video.videoHeight);
      if (box.width < 3 || box.height < 3) return;
      const width = Math.min(SAMPLE_WIDTH, box.width);
      const height = Math.max(3, Math.round((box.height * width) / box.width));
      canvas.width = width;
      canvas.height = height;
      try {
        context.drawImage(video, box.x, box.y, box.width, box.height, 0, 0, width, height);
        const { quality: next, gray } = scoreImage(context.getImageData(0, 0, width, height), previous);
        previous = gray;
        setQuality((last) => smoothQuality(last, next));
      } catch {
        // A frame that can't be read (a tainted or not-yet-decoded source) is skipped.
      }
    }, SAMPLE_EVERY_MS);
    return () => window.clearInterval(id);
  }, [enabled, videoRef]);
  return quality;
}

/** Scores one still image (the extracted muzzle frame) once it loads. Same-origin URLs only. */
export function useImageQuality(src: string | null | undefined): ScanQuality | null {
  const [quality, setQuality] = useState<ScanQuality | null>(null);
  useEffect(() => {
    setQuality(null);
    if (!src) return;
    let cancelled = false;
    const image = new Image();
    image.decoding = "async";
    image.onload = () => {
      if (cancelled || !image.naturalWidth) return;
      const { canvas, context } = sampler();
      if (!context) return;
      const width = Math.min(SAMPLE_WIDTH, image.naturalWidth);
      const height = Math.max(3, Math.round((image.naturalHeight * width) / image.naturalWidth));
      canvas.width = width;
      canvas.height = height;
      try {
        context.drawImage(image, 0, 0, width, height);
        setQuality(scoreImage(context.getImageData(0, 0, width, height)).quality);
      } catch {
        setQuality(null);
      }
    };
    image.src = src;
    return () => {
      cancelled = true;
    };
  }, [src]);
  return quality;
}

/**
 * The live capture-quality meter, set on the black camera view under the guide box. It fills as the muzzle
 * gets sharp, lit, and steady. A hint about the picture, never about identity: the label says so.
 */
export function QualityMeter({ quality, className }: { quality: ScanQuality | null; className?: string }) {
  const percent = quality ? Math.round(quality.score * 100) : 0;
  const good = quality?.status === "good";
  const Icon = good ? CircleCheck : TriangleAlert;
  const labelId = useId();
  return (
    <div className={cn("flex flex-col gap-1.5 rounded-control bg-shell/90 px-3 py-2 text-on-shell", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-sm font-bold" id={labelId}>
          Capture quality
        </span>
        <span className="text-sm text-on-shell-muted">a hint about the picture, not identity confidence</span>
      </div>
      <div
        role="meter"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={quality ? `${percent}%, ${STATUS_COPY[quality.status]}` : "Measuring"}
        className="h-2.5 overflow-hidden rounded-pill bg-shell-2"
      >
        <div
          className={cn(
            "h-full rounded-pill transition-[width] duration-(--dur-fast) ease-out-quart",
            good ? "bg-on-shell" : "bg-uncertain",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="flex items-center gap-2 font-bold" aria-live="polite">
        {quality ? (
          <>
            <Icon aria-hidden="true" className={cn("size-4 flex-none", good ? "text-on-shell" : "text-uncertain")} strokeWidth={2.5} />
            <span>{STATUS_COPY[quality.status]}</span>
            <Mono className="ml-auto text-sm font-regular text-on-shell-muted">{percent}%</Mono>
          </>
        ) : (
          <span className="text-on-shell-muted">Measuring the picture in the box…</span>
        )}
      </p>
    </div>
  );
}

/** The same scorer, after the fact, on the muzzle frame the video upload produced. */
export function FrameQualityReadout({ src }: { src: string | null | undefined }) {
  const quality = useImageQuality(src);
  if (!quality) return null;
  // A still has no motion, so its status is good, dark, bright, or soft.
  const good = quality.status === "good";
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {good ? (
        <CircleCheck aria-hidden="true" className="size-4 flex-none text-ok" strokeWidth={2.5} />
      ) : (
        <TriangleAlert aria-hidden="true" className="size-4 flex-none text-uncertain" strokeWidth={2.5} />
      )}
      <span>
        Capture quality <Mono className="font-bold">{Math.round(quality.score * 100)}%</Mono> ·{" "}
        {good ? "sharp enough" : STATUS_COPY[quality.status].split(" · ")[0]!.toLowerCase()}
      </span>
      <span className="text-muted">(a hint about the picture, not identity confidence)</span>
    </p>
  );
}
