import { ArrowLeft, RotateCw } from "lucide-react";
import { Button } from "../../components/Button";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono } from "../../components/figures";

export type ProcessingPhase = "creating" | "uploading" | "processing";

export interface ProcessingStepProps {
  phase: ProcessingPhase;
  /** Upload progress 0–1, or null while the browser can't tell. */
  progress: number | null;
  jobStatus?: string | null;
  enrollmentId?: string | null;
  error?: unknown;
  onRetry: () => void;
  onBack: () => void;
}

const JOB_COPY: Record<string, string> = {
  queued: "Waiting for the enrollment worker…",
  running: "Finding the muzzle, teeth, and body views, then checking the muzzle against the herd…",
  succeeded: "Done. Loading what it found…",
  failed: "Processing failed.",
};

function statusText(phase: ProcessingPhase, progress: number | null, jobStatus?: string | null): string {
  if (phase === "creating") return "Opening the enrollment…";
  if (phase === "uploading") {
    return progress === null ? "Uploading the video…" : `Uploading the video · ${Math.round(progress * 100)}%`;
  }
  return JOB_COPY[jobStatus ?? "queued"] ?? "Processing…";
}

export function ProcessingStep({ phase, progress, jobStatus, enrollmentId, error, onRetry, onBack }: ProcessingStepProps) {
  const text = statusText(phase, progress, jobStatus);
  if (error) {
    return (
      <div className="flex max-w-[64ch] flex-col gap-4">
        <ErrorNotice
          error={error}
          title={phase === "uploading" ? "The video didn't upload" : "The enrollment couldn't be processed"}
          onRetry={onRetry}
        />
        <div>
          <Button variant="ghost" icon={ArrowLeft} onClick={onBack}>
            Back to capture
          </Button>
        </div>
      </div>
    );
  }
  const determinate = phase === "uploading" && progress !== null;
  return (
    <LoadingRegion label={text}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <p className="text-md font-bold" aria-hidden="true">
            {text}
          </p>
          <div
            role="progressbar"
            aria-label="Enrollment progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={determinate ? Math.round(progress * 100) : undefined}
            className="h-2 w-full max-w-xl overflow-hidden rounded-pill bg-surface-2"
          >
            <div
              className={determinate ? "h-full bg-ink transition-[width] duration-(--dur-base)" : "progress-indeterminate h-full bg-ink"}
              style={determinate ? { width: `${Math.round(progress * 100)}%` } : undefined}
            />
          </div>
          {enrollmentId && (
            <p className="text-sm text-muted">
              Enrollment <Mono>{enrollmentId}</Mono>
              {jobStatus ? (
                <>
                  {" "}
                  · job <Mono>{jobStatus}</Mono>
                </>
              ) : null}
            </p>
          )}
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {["Muzzle", "Teeth", "Body"].map((label) => (
            <div key={label} className="flex flex-col gap-3">
              <Skeleton height="auto" className="aspect-[4/3]" />
              <Skeleton lines={2} />
            </div>
          ))}
        </div>
        <div>
          <Button variant="ghost" icon={RotateCw} onClick={onBack}>
            Cancel and start over
          </Button>
        </div>
      </div>
    </LoadingRegion>
  );
}
