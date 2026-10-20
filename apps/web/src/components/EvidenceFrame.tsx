import { CameraOff } from "lucide-react";
import { cn } from "../lib/cn";
import { Timestamp } from "./figures";
import { Provenance, type Source } from "./Provenance";
import { StatusPill, type StatusTone } from "./StatusPill";

export type EvidenceView = "muzzle" | "teeth" | "body";

const VIEW_LABEL: Record<EvidenceView, string> = {
  muzzle: "Muzzle",
  teeth: "Teeth",
  body: "Body",
};

const CORNERS = ["tl", "tr", "br", "bl"] as const;

export interface EvidenceQuality {
  /** Plain label: "Sharp", "Slight blur", "Too dark". */
  label: string;
  tone: Extract<StatusTone, "ok" | "uncertain" | "danger">;
}

export interface EvidenceFrameProps {
  view: EvidenceView;
  /** Signed media URL; when absent the frame says so plainly. */
  src?: string | null;
  alt?: string;
  capturedAt?: string | null;
  quality?: EvidenceQuality | null;
  source?: Source;
  className?: string;
}

/**
 * A registered 4:3 frame: every muzzle, teeth, and body view sits in the same frame with the
 * same corner marks, so evidence from different visits compares at a glance.
 */
export function EvidenceFrame({ view, src, alt, capturedAt, quality, source, className }: EvidenceFrameProps) {
  const label = VIEW_LABEL[view];
  return (
    <figure className={cn("flex min-w-0 flex-col gap-3", className)}>
      <div className="evidence-frame" data-missing={src ? undefined : ""}>
        {src ? (
          <img src={src} alt={alt ?? `${label} view`} loading="lazy" decoding="async" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
            <CameraOff aria-hidden="true" className="size-8 text-muted" strokeWidth={2} />
            <p className="font-bold">No footage attached</p>
            <p className="text-sm text-muted">Capture the {label.toLowerCase()} view during enrollment to add it.</p>
          </div>
        )}
        {CORNERS.map((corner) => (
          <svg key={corner} className="reg-mark" data-corner={corner} viewBox="0 0 18 18" aria-hidden="true" focusable="false">
            <path d="M1.5 18V1.5H18" fill="none" stroke="currentColor" strokeWidth="3" />
          </svg>
        ))}
      </div>
      <figcaption className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span className="font-bold">{label}</span>
          {capturedAt ? (
            <Timestamp value={capturedAt} mode="absolute" className="text-sm text-muted" />
          ) : (
            <span className="text-sm text-muted">Not captured</span>
          )}
        </div>
        {(quality || source) && (
          <div className="flex flex-wrap items-center gap-2">
            {quality && <StatusPill tone={quality.tone} label={quality.label} />}
            {source && <Provenance source={source} />}
          </div>
        )}
      </figcaption>
    </figure>
  );
}
