import { FileVideo, Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { Provenance } from "../../components/Provenance";
import { cn } from "../../lib/cn";
import { Recorder } from "./Recorder";
import { DEMO_SAMPLES } from "./samples";

const MAX_BYTES = 200 * 1024 * 1024;
const VIDEO_EXT = /\.(mp4|webm|mov)$/i;
const VIDEO_TYPES = new Set(["video/mp4", "video/webm", "video/quicktime"]);

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** The demo's phone enrollment video (demo/media/veo/video_hp.mp4), served by the API in demo mode. */
export const PHONE_VIDEO = { url: "/api/v1/demo/footage/video_hp.mp4", filename: "video_hp.mp4" } as const;

/**
 * Fetches the AI-generated phone video and hands it to the normal upload, so the real pipeline runs on it.
 */
function PhoneVideoDemo({ onVideo, busy }: { onVideo: (file: Blob, filename: string) => void; busy?: boolean }) {
  const headingId = useId();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function use() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(PHONE_VIDEO.url);
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      onVideo(new Blob([blob], { type: "video/mp4" }), PHONE_VIDEO.filename);
    } catch {
      setError("The phone video couldn't load. It is served only in demo mode, after `git lfs pull`. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 id={headingId} className="text-md font-bold">
          Use the phone enrollment video
        </h2>
      </div>
      <p className="text-sm text-muted">
        An 8-second phone enrollment video: the muzzle, the teeth, then the full side. It goes through the real upload
        and processing, so the review names whatever the video doesn't show.
      </p>
      {error && (
        <p role="alert" className="text-sm font-bold text-danger">
          {error}
        </p>
      )}
      <div>
        <Button variant="secondary" icon={FileVideo} disabled={busy} loading={loading} loadingLabel="Loading the video…" onClick={() => void use()}>
          Use the phone enrollment video
        </Button>
      </div>
    </section>
  );
}

export interface CaptureStepProps {
  onVideo: (file: Blob, filename: string) => void;
  onSample: (sampleKey: string) => void;
  busy?: boolean;
}

export function CaptureStep({ onVideo, onSample, busy }: CaptureStepProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadHeadingId = useId();
  const sampleHeadingId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function choose(next: File | undefined) {
    if (!next) return;
    if (!VIDEO_TYPES.has(next.type) && !VIDEO_EXT.test(next.name)) {
      setFile(null);
      setFileError("That file isn't a video VEYRA can read. Choose an MP4, WebM, or MOV file.");
      return;
    }
    if (next.size > MAX_BYTES) {
      setFile(null);
      setFileError(`That video is ${formatSize(next.size)}. The limit is 200 MB; trim it and try again.`);
      return;
    }
    setFileError(null);
    setFile(next);
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)] lg:gap-8">
      <section aria-label="Record with this device's camera" className="min-w-0">
        <Recorder onUse={onVideo} onChooseUpload={() => fileRef.current?.click()} disabled={busy} />
      </section>

      <div className="flex min-w-0 flex-col gap-10">
        <section aria-labelledby={uploadHeadingId} className="flex flex-col gap-3">
          <h2 id={uploadHeadingId} className="text-md font-bold">
            Upload a prepared video
          </h2>
          <label
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              choose(event.dataTransfer.files[0]);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-start gap-2 rounded-panel border-2 border-dashed px-5 py-5 transition-colors",
              "has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink",
              dragging ? "border-ink bg-surface-2" : "border-line-strong hover:bg-surface",
            )}
          >
            <span className="flex items-center gap-2 font-bold">
              <Upload aria-hidden="true" className="size-5" strokeWidth={2.25} />
              Choose a video, or drop it here
            </span>
            <span className="text-sm text-muted">MP4, WebM, or MOV, one continuous take, up to 200 MB.</span>
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
              className="sr-only"
              onChange={(event) => choose(event.target.files?.[0])}
            />
          </label>
          {fileError && (
            <p role="alert" className="text-sm font-bold text-danger">
              {fileError}
            </p>
          )}
          {file && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
              <span className="flex min-w-0 items-center gap-2">
                <FileVideo aria-hidden="true" className="size-5 flex-none" strokeWidth={2.25} />
                <span className="min-w-0 truncate font-bold">{file.name}</span>
                <span className="figures flex-none text-sm text-muted">{formatSize(file.size)}</span>
              </span>
              <Button variant="primary" disabled={busy} onClick={() => onVideo(file, file.name)}>
                Use this video
              </Button>
            </div>
          )}
        </section>

        <PhoneVideoDemo onVideo={onVideo} busy={busy} />

        <section aria-labelledby={sampleHeadingId} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h2 id={sampleHeadingId} className="text-md font-bold">
              Use prepared demo sample
            </h2>
            <Provenance source="simulated" />
          </div>
          <p className="text-sm text-muted">
            For a demo without footage. The views, match, and estimates are simulated, and are labeled that way on every
            screen they reach.
          </p>
          <ul className="flex flex-col border-t border-line">
            {DEMO_SAMPLES.map((sample) => (
              <li key={sample.key} className="flex flex-wrap items-center justify-between gap-3 border-b border-line py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-bold">{sample.label}</p>
                  <p className="text-sm text-muted">{sample.expect}</p>
                  <p className="figures text-xs text-muted">{sample.key}</p>
                </div>
                <Button variant="secondary" disabled={busy} onClick={() => onSample(sample.key)}>
                  Use sample
                </Button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
