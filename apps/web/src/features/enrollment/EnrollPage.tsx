import { useQueryClient } from "@tanstack/react-query";
import { ClipboardList, FileText, RotateCcw, ScanLine } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { animalsQueryKey } from "../../app/use-shell-summary";
import { Button, ButtonLink } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice } from "../../components/feedback";
import { Mono } from "../../components/figures";
import { PageHeader } from "../../components/layout";
import { useRole } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import {
  createEnrollment,
  getEnrollment,
  processEnrollment,
  retryEnrollment,
  uploadVideo,
  waitForProcessing,
} from "./api";
import { CaptureStep } from "./CaptureStep";
import { ConfirmStep } from "./ConfirmStep";
import "./enrollment.css";
import { ProcessingStep, type ProcessingPhase } from "./ProcessingStep";
import { ReviewStep } from "./ReviewStep";
import type { Decision, Enrollment } from "./rules";
import { Stepper } from "./Stepper";

type Source = { kind: "sample"; key: string } | { kind: "video"; file: Blob; filename: string };

type Flow =
  | { step: "capture"; notice?: string }
  | {
      step: "processing";
      phase: ProcessingPhase;
      progress: number | null;
      enrollmentId: string | null;
      jobStatus: string | null;
      error: unknown;
      source: Source | null;
    }
  | { step: "review"; enrollment: Enrollment }
  | { step: "confirm"; enrollment: Enrollment; decision: Decision; linkTo: string | null }
  | { step: "done"; enrollment: Enrollment; animal: { id: string | null; name: string | null } };

const STEP_INDEX: Record<Flow["step"], number> = { capture: 0, processing: 1, review: 2, confirm: 3, done: 3 };

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function DoneStep({
  enrollment,
  animal,
  onRestart,
  onRetry,
  retrying,
}: {
  enrollment: Enrollment;
  animal: { id: string | null; name: string | null };
  onRestart: () => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const decision = (enrollment.decision ?? {}) as Record<string, unknown>;
  const outcome = decision.outcome;
  if (enrollment.status === "rejected") {
    return (
      <div className="flex max-w-[64ch] flex-col items-start gap-4">
        <h2 className="text-lg font-bold">Enrollment rejected</h2>
        <p>
          The record is kept with your reason
          {typeof decision.reject_reason === "string" && (
            <>
              : <q>{decision.reject_reason}</q>
            </>
          )}
          . No animal was created.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" icon={RotateCcw} onClick={onRetry} loading={retrying} loadingLabel="Starting again…">
            Retry this enrollment
          </Button>
          <Button variant="secondary" icon={ScanLine} onClick={onRestart}>
            Enroll another
          </Button>
        </div>
      </div>
    );
  }
  const id = animal.id ?? enrollment.animal_id ?? "";
  const pending = decision.identity_status === "pending_review";
  const name = animal.name ?? id;
  const passport = `/animals/${encodeURIComponent(id)}`;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <EarTag animalId={id} state={pending ? "pending" : "confirmed"} size="xl" />
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-xl font-bold" role="status">
            {outcome === "link_existing" ? (
              <>
                Views linked to {name} <Mono>({id})</Mono>
              </>
            ) : (
              <>
                {name} is enrolled as <Mono>{id}</Mono>
              </>
            )}
          </h2>
          <p className="max-w-[62ch] text-muted">
            {outcome === "link_existing"
              ? "The new muzzle, teeth, and body frames are added to its references. Its valuation is unchanged."
              : pending
                ? "Identity pending review: the tag is provisional, and financial actions stay blocked until it is confirmed."
                : "Identity confirmed. The estimates are on the passport; the valuation waits for your confirmation."}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        <ButtonLink to={passport} variant="primary" icon={ClipboardList}>
          Open passport
        </ButtonLink>
        {outcome !== "link_existing" && (
          <ButtonLink to={`${passport}#valuation`} variant="secondary" icon={FileText}>
            Confirm valuation
          </ButtonLink>
        )}
        <Button variant="ghost" icon={ScanLine} onClick={onRestart}>
          Enroll another
        </Button>
      </div>
    </div>
  );
}

export function EnrollPage() {
  const role = useRole();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [flow, setFlow] = useState<Flow>({ step: "capture" });
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<unknown>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resumeId = params.get("enrollment");
  const resumedRef = useRef(false);

  const remember = useCallback(
    (enrollmentId: string | null) => {
      // An ID this page wrote itself is already in hand; only an ID arriving with the URL is resumed.
      if (enrollmentId) resumedRef.current = true;
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (enrollmentId) next.set("enrollment", enrollmentId);
          else next.delete("enrollment");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  const toReviewOrFailure = useCallback((enrollment: Enrollment, source: Source | null) => {
    if (enrollment.status === "review") setFlow({ step: "review", enrollment });
    else if (enrollment.status === "confirmed" || enrollment.status === "rejected")
      setFlow({ step: "done", enrollment, animal: { id: enrollment.animal_id, name: null } });
    else
      setFlow({
        step: "processing",
        phase: "processing",
        progress: null,
        enrollmentId: enrollment.id,
        jobStatus: enrollment.job?.status ?? "failed",
        error: new Error("processing_failed"),
        source,
      });
  }, []);

  /** Process an enrollment that already has its video (or a sample), then land on review. */
  const processExisting = useCallback(
    async (enrollmentId: string, source: Source | null, signal: AbortSignal) => {
      setFlow({ step: "processing", phase: "processing", progress: null, enrollmentId, jobStatus: "queued", error: null, source });
      const jobId = await processEnrollment(enrollmentId);
      const enrollment = await waitForProcessing(
        enrollmentId,
        jobId,
        (job) => setFlow((f) => (f.step === "processing" ? { ...f, jobStatus: job.status } : f)),
        signal,
      );
      toReviewOrFailure(enrollment, source);
    },
    [toReviewOrFailure],
  );

  const run = useCallback(
    async (source: Source) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const { signal } = controller;
      let enrollmentId: string | null = null;
      let phase: ProcessingPhase = "creating";
      setFlow({ step: "processing", phase, progress: null, enrollmentId: null, jobStatus: null, error: null, source });
      try {
        const created = await createEnrollment(source.kind === "sample" ? source.key : null);
        enrollmentId = created.id;
        remember(enrollmentId);
        if (source.kind === "video") {
          phase = "uploading";
          setFlow((f) => (f.step === "processing" ? { ...f, phase, enrollmentId, progress: 0 } : f));
          await uploadVideo(
            created.id,
            source.file,
            source.filename,
            (progress) => setFlow((f) => (f.step === "processing" ? { ...f, progress } : f)),
            signal,
          );
        }
        phase = "processing";
        await processExisting(created.id, source, signal);
      } catch (error) {
        if (isAbort(error)) return;
        setFlow({ step: "processing", phase, progress: null, enrollmentId, jobStatus: null, error, source });
      }
    },
    [processExisting, remember],
  );

  // Coming back to /enroll?enrollment=… picks the enrollment up where it stands.
  useEffect(() => {
    if (!resumeId || resumedRef.current || flow.step !== "capture") return;
    resumedRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setFlow({ step: "processing", phase: "processing", progress: null, enrollmentId: resumeId, jobStatus: null, error: null, source: null });
    void (async () => {
      try {
        const enrollment = await getEnrollment(resumeId);
        if (enrollment.status === "processing" && enrollment.job) {
          const done = await waitForProcessing(
            resumeId,
            enrollment.job.id,
            (job) => setFlow((f) => (f.step === "processing" ? { ...f, jobStatus: job.status } : f)),
            controller.signal,
          );
          toReviewOrFailure(done, null);
        } else if (enrollment.status === "created" || enrollment.status === "uploaded") {
          if (enrollment.sample_key || enrollment.video_media_id) await processExisting(resumeId, null, controller.signal);
          else {
            remember(null);
            setFlow({ step: "capture" });
          }
        } else {
          toReviewOrFailure(enrollment, null);
        }
      } catch (error) {
        if (isAbort(error)) return;
        remember(null);
        setFlow({ step: "capture", notice: "That enrollment couldn't be opened. Start a new one." });
      }
    })();
  }, [resumeId, flow.step, processExisting, toReviewOrFailure, remember]);

  const restart = useCallback(() => {
    abortRef.current?.abort();
    remember(null);
    setRetryError(null);
    setFlow({ step: "capture" });
  }, [remember]);

  /** Retry creates a new enrollment from the old one; a sample processes again at once, a video needs a new take. */
  const retry = useCallback(
    async (enrollment: Enrollment) => {
      setRetrying(true);
      setRetryError(null);
      try {
        const created = await retryEnrollment(enrollment.id);
        remember(created.id);
        if (created.sample_key) {
          const controller = new AbortController();
          abortRef.current = controller;
          await processExisting(created.id, { kind: "sample", key: created.sample_key }, controller.signal);
        } else {
          setFlow({ step: "capture", notice: "Record or upload the video again for the new attempt." });
        }
      } catch (error) {
        if (!isAbort(error)) setRetryError(error);
      } finally {
        setRetrying(false);
      }
    },
    [processExisting, remember],
  );

  const canEnroll = role.role === "manager" || role.role === "operator";
  const stepIndex = STEP_INDEX[flow.step];

  return (
    <Page>
      <PageHeader title="Enroll an animal" meta="One continuous video: the muzzle, the teeth, then the full side with the marker." />
      {!canEnroll ? (
        <EmptyState title="Vets can't enroll animals" icon={ScanLine}>
          Enrollment is for managers and operators. Switch the role in the top bar to Manager or Operator to enroll.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-8">
          <Stepper current={stepIndex} done={flow.step === "done"} />
          {retryError ? <ErrorNotice error={retryError} title="The retry couldn't start" /> : null}

          {flow.step === "capture" && (
            <>
              {flow.notice && <p className="rounded-control border-2 border-uncertain bg-uncertain-soft p-4">{flow.notice}</p>}
              <CaptureStep
                onSample={(key) => void run({ kind: "sample", key })}
                onVideo={(file, filename) => void run({ kind: "video", file, filename })}
              />
            </>
          )}

          {flow.step === "processing" && (
            <ProcessingStep
              phase={flow.phase}
              progress={flow.progress}
              jobStatus={flow.jobStatus}
              enrollmentId={flow.enrollmentId}
              error={flow.error}
              onBack={restart}
              onRetry={() => {
                if (flow.source) void run(flow.source);
                else restart();
              }}
            />
          )}

          {flow.step === "review" && (
            <ReviewStep
              enrollment={flow.enrollment}
              onDecide={(decision, linkTo) => setFlow({ step: "confirm", enrollment: flow.enrollment, decision, linkTo })}
              onRetake={() => void retry(flow.enrollment)}
              retaking={retrying}
            />
          )}

          {flow.step === "confirm" && (
            <ConfirmStep
              key={flow.enrollment.id}
              enrollment={flow.enrollment}
              decision={flow.decision}
              linkTo={flow.linkTo}
              onDecisionChange={(decision, linkTo) => setFlow({ ...flow, decision, linkTo })}
              onBack={() => setFlow({ step: "review", enrollment: flow.enrollment })}
              onRecheck={() => void retry(flow.enrollment)}
              rechecking={retrying}
              onConfirmed={(enrollment, animal) => {
                void queryClient.invalidateQueries({ queryKey: animalsQueryKey });
                setFlow({ step: "done", enrollment, animal });
              }}
            />
          )}

          {flow.step === "done" && (
            <DoneStep
              enrollment={flow.enrollment}
              animal={flow.animal}
              onRestart={restart}
              onRetry={() => void retry(flow.enrollment)}
              retrying={retrying}
            />
          )}
        </div>
      )}
    </Page>
  );
}

