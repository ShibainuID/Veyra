import { Camera, CameraOff, ChevronRight, Circle, RotateCcw, Square, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { cn } from "../../lib/cn";
import { formatCountdown } from "../../lib/format";
import { CAPTURE_PROMPTS, muzzleGuideBox, promptIndexAt } from "./guide-box";
import { QualityMeter, useLiveScanQuality } from "./QualityMeter";

type RecorderState =
  | { kind: "idle" }
  | { kind: "requesting" }
  | { kind: "blocked"; title: string; detail: string }
  | { kind: "ready" }
  | { kind: "recording" }
  | { kind: "recorded"; blob: Blob; url: string; seconds: number };

const MIME_CANDIDATES = ["video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
}

function blockedFor(error: unknown): { title: string; detail: string } {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return {
      title: "Camera access was denied",
      detail: "Allow the camera for this site in the browser's settings, or upload a video you recorded earlier.",
    };
  }
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") {
    return { title: "No camera found", detail: "This device has no camera VEYRA can use. Upload a video instead." };
  }
  if (name === "NotReadableError") {
    return {
      title: "The camera is busy",
      detail: "Another app is using the camera. Close it and try again, or upload a video instead.",
    };
  }
  return { title: "The camera couldn't start", detail: "Try again, or upload a video instead." };
}

function extensionFor(type: string): string {
  if (type.includes("mp4")) return "mp4";
  if (type.includes("quicktime")) return "mov";
  return "webm";
}

export interface RecorderProps {
  onUse: (blob: Blob, filename: string) => void;
  onChooseUpload: () => void;
  disabled?: boolean;
}

/**
 * One continuous guided recording. The live view carries the muzzle guide box at exactly the ML crop's
 * geometry (90% of the frame width, 1.18 aspect, centred), and the prompts walk muzzle, teeth, then body,
 * advancing on their own or when the operator taps ahead.
 */
export function Recorder({ onUse, onChooseUpload, disabled }: RecorderProps) {
  const [state, setState] = useState<RecorderState>({ kind: "idle" });
  const [dims, setDims] = useState<{ w: number; h: number }>({ w: 16, h: 9 });
  const [elapsed, setElapsed] = useState(0);
  const [tapped, setTapped] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const startedRef = useRef(0);
  const urlRef = useRef<string | null>(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(
    () => () => {
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      stopStream();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [stopStream],
  );

  const startCamera = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState({
        kind: "blocked",
        title: "Camera capture isn't available here",
        detail: "The browser only allows the camera on a secure (https) page. Upload a video instead.",
      });
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setState({
        kind: "blocked",
        title: "This browser can't record video",
        detail: "Record with the device's camera app, then upload the video here.",
      });
      return;
    }
    setState({ kind: "requesting" });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      streamRef.current = stream;
      setState({ kind: "ready" });
    } catch (error) {
      setState({ kind: "blocked", ...blockedFor(error) });
    }
  }, []);

  // Attach the live stream whenever the live view is on screen.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (state.kind === "ready" || state.kind === "recording") {
      if (video.srcObject !== streamRef.current) video.srcObject = streamRef.current;
      void video.play().catch(() => undefined);
    }
  }, [state.kind]);

  // The recording clock.
  useEffect(() => {
    if (state.kind !== "recording") return;
    const id = window.setInterval(() => setElapsed((Date.now() - startedRef.current) / 1000), 250);
    return () => window.clearInterval(id);
  }, [state.kind]);

  const startRecording = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    const mimeType = pickMimeType();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch {
      setState({ kind: "blocked", title: "This browser can't record video", detail: "Upload a video instead." });
      return;
    }
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "video/webm" });
      const url = URL.createObjectURL(blob);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = url;
      stopStream();
      setState({ kind: "recorded", blob, url, seconds: (Date.now() - startedRef.current) / 1000 });
    };
    recorderRef.current = recorder;
    startedRef.current = Date.now();
    setElapsed(0);
    setTapped(0);
    recorder.start(1000);
    setState({ kind: "recording" });
  }, [stopStream]);

  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const promptIndex = Math.max(tapped, promptIndexAt(elapsed));
  const prompt = CAPTURE_PROMPTS[promptIndex]!;
  const box = muzzleGuideBox(dims.w, dims.h);
  const live = state.kind === "ready" || state.kind === "recording";
  const aspect = dims.w / dims.h;
  const scoring = live && prompt.view === "muzzle";
  const quality = useLiveScanQuality(videoRef, scoring);

  return (
    <div className="flex flex-col gap-4">
      <div
        className="relative mx-auto overflow-hidden rounded-panel bg-shell text-on-shell"
        style={{ aspectRatio: `${dims.w} / ${dims.h}`, width: `min(100%, calc(64vh * ${aspect.toFixed(4)}))` }}
      >
        {state.kind === "recorded" ? (
          <video src={state.url} controls playsInline className="size-full bg-shell object-contain" aria-label="Recorded video preview" />
        ) : (
          <video
            ref={videoRef}
            muted
            playsInline
            autoPlay
            aria-label="Live camera view"
            className={cn("size-full object-cover", !live && "invisible")}
            onLoadedMetadata={(event) => {
              const v = event.currentTarget;
              if (v.videoWidth && v.videoHeight) setDims({ w: v.videoWidth, h: v.videoHeight });
            }}
          />
        )}

        {live && (
          <svg
            viewBox={`0 0 ${dims.w} ${dims.h}`}
            preserveAspectRatio="none"
            className="pointer-events-none absolute inset-0 size-full"
            aria-hidden="true"
          >
            {/* Scrim outside the box, then the box itself: the exact region the muzzle crop takes. */}
            <path
              d={`M0 0H${dims.w}V${dims.h}H0Z M${box.x} ${box.y}h${box.width}v${box.height}h${-box.width}Z`}
              fillRule="evenodd"
              fill="oklch(0.17 0 0 / 0.42)"
              opacity={prompt.view === "muzzle" ? 1 : 0.35}
            />
            <rect
              x={box.x}
              y={box.y}
              width={box.width}
              height={box.height}
              fill="none"
              stroke="var(--tag)"
              strokeWidth={Math.max(3, dims.w * 0.006)}
              strokeDasharray={prompt.view === "muzzle" ? undefined : `${dims.w * 0.02} ${dims.w * 0.015}`}
              opacity={prompt.view === "muzzle" ? 1 : 0.6}
            />
          </svg>
        )}

        {live && (
          <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-3 p-3 sm:p-4">
            <div className="max-w-[30rem] rounded-control bg-shell/90 px-3 py-2" aria-live="polite">
              <p className="figures text-sm text-on-shell-muted">
                View {promptIndex + 1} of {CAPTURE_PROMPTS.length}
              </p>
              <p className="font-bold text-tag">{prompt.title}</p>
              <p className="hidden text-sm text-on-shell-muted sm:block">{prompt.detail}</p>
            </div>
            {state.kind === "recording" && (
              <p className="figures flex flex-none items-center gap-2 rounded-control bg-shell/90 px-3 py-2 font-bold">
                <Circle aria-hidden="true" className="size-3 fill-danger text-danger" />
                <span className="sr-only">Recording, </span>
                {formatCountdown(elapsed * 1000)}
              </p>
            )}
          </div>
        )}

        {scoring && (
          <div className="absolute inset-x-0 bottom-0 p-3 sm:p-4">
            <QualityMeter quality={quality} className="mx-auto max-w-[30rem]" />
          </div>
        )}

        {!live && state.kind !== "recorded" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            {state.kind === "blocked" ? (
              <>
                <CameraOff aria-hidden="true" className="size-9 text-on-shell-muted" strokeWidth={2} />
                <p role="alert" className="text-md font-bold">
                  {state.title}
                </p>
                <p className="max-w-[44ch] text-on-shell-muted">{state.detail}</p>
              </>
            ) : (
              <>
                <Camera aria-hidden="true" className="size-9 text-on-shell-muted" strokeWidth={2} />
                <p className="text-md font-bold">Record one continuous video</p>
                <p className="max-w-[46ch] text-on-shell-muted">
                  Muzzle, then teeth, then the full side with the marker on the flank. The rear camera is used when the
                  device has one.
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {(state.kind === "idle" || state.kind === "requesting") && (
          <Button
            variant="primary"
            icon={Camera}
            onClick={() => void startCamera()}
            loading={state.kind === "requesting"}
            loadingLabel="Waiting for the camera…"
            disabled={disabled}
          >
            Start camera
          </Button>
        )}
        {state.kind === "blocked" && (
          <>
            <Button variant="primary" icon={Upload} onClick={onChooseUpload}>
              Upload a video instead
            </Button>
            <Button variant="secondary" icon={RotateCcw} onClick={() => void startCamera()}>
              Try the camera again
            </Button>
          </>
        )}
        {state.kind === "ready" && (
          <Button variant="primary" icon={Circle} onClick={startRecording} disabled={disabled}>
            Start recording
          </Button>
        )}
        {state.kind === "recording" && (
          <>
            {promptIndex < CAPTURE_PROMPTS.length - 1 ? (
              <Button variant="primary" icon={ChevronRight} onClick={() => setTapped(promptIndex + 1)}>
                Next view: {CAPTURE_PROMPTS[promptIndex + 1]!.view}
              </Button>
            ) : null}
            <Button variant={promptIndex === CAPTURE_PROMPTS.length - 1 ? "primary" : "secondary"} icon={Square} onClick={stopRecording}>
              Stop recording
            </Button>
          </>
        )}
        {state.kind === "recorded" && (
          <>
            <Button
              variant="primary"
              disabled={disabled}
              onClick={() => onUse(state.blob, `enrollment-${Date.now()}.${extensionFor(state.blob.type)}`)}
            >
              Use this video
            </Button>
            <Button variant="secondary" icon={RotateCcw} onClick={() => void startCamera()}>
              Record again
            </Button>
            <p className="figures text-sm text-muted">{formatCountdown(state.seconds * 1000)} recorded</p>
          </>
        )}
      </div>
    </div>
  );
}
