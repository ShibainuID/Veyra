import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, ClipboardList, FilePlus2, MessageSquarePlus, Stethoscope, VideoOff } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Link } from "react-router";
import { Button, ButtonLink } from "../../components/Button";
import { Drawer } from "../../components/Drawer";
import { EarTag } from "../../components/EarTag";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { Provenance } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatAbsolute, formatClock } from "../../lib/format";
import { ApiError } from "../../lib/errors";
import { useRole } from "../../lib/role-store";
import { toSource } from "../enrollment/ReviewStep";
import { monitorKeys } from "../monitor/api";
import {
  KIND_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
  alertNotes,
  alertSubject,
  comparison,
  ruleName,
  type AlertView,
} from "./alert-copy";

async function fetchAlert(alertId: string): Promise<AlertView> {
  const { data } = await api.GET("/api/v1/alerts/{alert_id}", { params: { path: { alert_id: alertId } } });
  if (!data) throw new ApiError(404, "NOT_FOUND", "Alert not found.");
  return data;
}

function Window({ label, start, end }: { label: string; start: string | null; end: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm font-bold text-muted">{label}</dt>
      <dd>
        {start && end ? (
          <span className="flex flex-wrap gap-x-2">
            <Timestamp value={start} mode="absolute" />
            <span aria-hidden="true">–</span>
            <span className="sr-only">to</span>
            {formatAbsolute(start).slice(0, -5) === formatAbsolute(end).slice(0, -5) ? (
              <time dateTime={end} className="figures">
                {formatClock(end)}
              </time>
            ) : (
              <Timestamp value={end} mode="absolute" />
            )}
          </span>
        ) : (
          <span className="text-muted">None recorded</span>
        )}
      </dd>
    </div>
  );
}

function Bars({ alert }: { alert: AlertView }) {
  const data = comparison(alert);
  if (!data) return <p className="text-muted">The rule recorded no figures to compare.</p>;
  const scale = (v: number) => `${Math.max(1.5, Math.min(100, (v / (data.max || 1)) * 100))}%`;
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-sm text-muted">{data.measure}</figcaption>
      <div className="relative flex flex-col gap-3">
        {data.bars.map((bar) => (
          <div key={bar.label} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_3.5rem] items-center gap-3">
            <span className="text-sm font-bold">{bar.label}</span>
            <span className="relative h-6 rounded-[4px] bg-surface-2">
              <span
                className={cn(
                  "absolute inset-y-0 left-0 rounded-[4px]",
                  bar.tone === "alert" ? "bg-uncertain" : bar.tone === "muted" ? "bg-line-strong" : "bg-ink",
                )}
                style={{ width: scale(bar.value) }}
              />
              {data.line && (
                <span
                  aria-hidden="true"
                  className="absolute -inset-y-1 w-0.5 bg-ink"
                  style={{ left: scale(data.line.value) }}
                />
              )}
            </span>
            <Mono className="text-right font-bold">{bar.display}</Mono>
          </div>
        ))}
      </div>
      {data.line && (
        <p className="flex items-center gap-2 text-sm">
          <span aria-hidden="true" className="inline-block h-4 w-0.5 bg-ink" />
          {data.line.label}
        </p>
      )}
    </figure>
  );
}

export interface AlertDrawerProps {
  alertId: string | null;
  onClose: () => void;
}

export function AlertDrawer({ alertId, onClose }: AlertDrawerProps) {
  const role = useRole();
  const toast = useToast();
  const queryClient = useQueryClient();
  const noteId = useId();
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: monitorKeys.alert(alertId ?? "none"),
    queryFn: () => fetchAlert(alertId!),
    enabled: alertId !== null,
    initialData: () => queryClient.getQueryData<AlertView[]>(monitorKeys.alerts)?.find((a) => a.id === alertId),
    initialDataUpdatedAt: 0,
  });
  const alert = query.data;

  const mutation = useMutation({
    mutationFn: async (body: { status?: "acknowledged" | "resolved"; note?: string }) => {
      const { data } = await api.PATCH("/api/v1/alerts/{alert_id}", { params: { path: { alert_id: alertId! } }, body });
      return data!;
    },
    onSuccess: (updated, body) => {
      queryClient.setQueryData(monitorKeys.alert(updated.id), updated);
      queryClient.setQueryData<AlertView[]>(monitorKeys.alerts, (all) => all?.map((a) => (a.id === updated.id ? updated : a)));
      void queryClient.invalidateQueries({ queryKey: monitorKeys.alerts });
      void queryClient.invalidateQueries({ queryKey: ["replays"] });
      setNote("");
      setNoteError(null);
      toast.show({
        title:
          body.status === "resolved"
            ? "Alert resolved"
            : body.status === "acknowledged"
              ? "Alert acknowledged"
              : role.role === "vet"
                ? "Assessment note added"
                : "Note added",
        tone: "ok",
      });
    },
  });

  const isVet = role.role === "vet";
  const canResolve = role.role === "manager" || role.role === "operator";
  const notes = alert ? alertNotes(alert) : [];
  const clip = (alert?.clip ?? null) as Record<string, unknown> | null;
  const clipVideo = clip && typeof clip.video === "string" ? clip.video : null;
  const source = toSource((alert?.rule as Record<string, unknown> | undefined)?.source);

  function requireNote(): string | null {
    const text = note.trim();
    if (!text) {
      setNoteError(isVet ? "Write the assessment first." : "Write a note first.");
      noteRef.current?.focus();
      return null;
    }
    return text;
  }

  const footer = alert && (
    <div className="flex flex-col gap-3">
      {mutation.error ? (
        <ErrorNotice error={mutation.error} title={mutation.error instanceof ApiError ? mutation.error.message : undefined} />
      ) : null}
      <div className="flex flex-wrap gap-3">
        {alert.status === "open" && (
          <Button
            variant="primary"
            icon={Check}
            loading={mutation.isPending && mutation.variables?.status === "acknowledged"}
            loadingLabel="Acknowledging…"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ status: "acknowledged", ...(note.trim() ? { note: note.trim() } : {}) })}
          >
            Acknowledge
          </Button>
        )}
        <Button
          variant={alert.status === "open" ? "secondary" : "primary"}
          icon={isVet ? Stethoscope : MessageSquarePlus}
          loading={mutation.isPending && !mutation.variables?.status}
          loadingLabel="Adding…"
          disabled={mutation.isPending || alert.status === "resolved"}
          onClick={() => {
            const text = requireNote();
            if (text) mutation.mutate({ note: text });
          }}
        >
          {isVet ? "Add assessment note" : "Add note"}
        </Button>
        {canResolve && alert.status !== "resolved" && (
          <Button
            variant="secondary"
            icon={CheckCheck}
            loading={mutation.isPending && mutation.variables?.status === "resolved"}
            loadingLabel="Resolving…"
            disabled={mutation.isPending}
            onClick={() => {
              const text = requireNote();
              if (text) mutation.mutate({ status: "resolved", note: text });
            }}
          >
            Resolve
          </Button>
        )}
      </div>
      {isVet && alert.status !== "resolved" && (
        <p className="text-sm text-muted">Vets acknowledge and add assessments; a manager or operator resolves.</p>
      )}
    </div>
  );

  return (
    <Drawer
      open={alertId !== null}
      onClose={onClose}
      title={alert ? `${KIND_LABEL[alert.kind]} · ${alertSubject(alert)}` : "Alert"}
      description={alert ? <Mono className="text-sm">{alert.id}</Mono> : undefined}
      footer={footer || undefined}
    >
      {query.isPending && !alert ? (
        <LoadingRegion label="Loading the alert">
          <Skeleton lines={6} />
        </LoadingRegion>
      ) : query.error && !alert ? (
        <ErrorNotice error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : alert ? (
        <div className="flex flex-col gap-7">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone={STATUS_TONE[alert.status]} label={STATUS_LABEL[alert.status]} />
              <Provenance source={source} />
            </div>
            <p className="text-md">{alert.summary}</p>
          </div>

          <section aria-label="Animal and camera" className="flex flex-col gap-4">
            {alert.animal_id ? (
              <div className="flex flex-wrap items-center gap-4">
                <EarTag animalId={alert.animal_id} state="confirmed" size="md" />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="text-md font-bold">{alert.animal_name ?? alert.animal_id}</span>
                  <Mono className="text-sm text-muted">{alert.animal_id}</Mono>
                </div>
                <ButtonLink to={`/animals/${encodeURIComponent(alert.animal_id)}`} icon={ClipboardList}>
                  Open passport
                </ButtonLink>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <EarTag state="none" size="md" />
                <p className="font-bold">
                  Unassigned track <Mono>{alert.track_key ?? "—"}</Mono> — cannot be linked to a passport
                </p>
              </div>
            )}
            <p className="text-sm">
              Camera <strong>{alert.camera_name}</strong> ·{" "}
              <Link
                to={`/monitor?camera=${encodeURIComponent(alert.camera_id)}${alert.animal_id ? `&animal=${encodeURIComponent(alert.animal_id)}` : ""}`}
                className="font-bold"
              >
                Show on the pen map
              </Link>
            </p>
          </section>

          <section aria-labelledby={`${noteId}-win`} className="flex flex-col gap-4">
            <h3 id={`${noteId}-win`} className="text-md font-bold">
              Observation against baseline
            </h3>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Window label="Observation window" start={alert.window_start} end={alert.window_end} />
              <Window
                label={alert.kind === "reduced_movement" ? "Baseline window" : "Baseline"}
                start={alert.baseline_start}
                end={alert.baseline_end}
              />
            </dl>
            <Bars alert={alert} />
            <p className="text-sm text-muted">
              Rule <Mono className="text-ink">{ruleName(alert) ?? "unnamed"}</Mono>
              {typeof (alert.rule as Record<string, unknown>).text === "string" && (
                <>: {(alert.rule as Record<string, unknown>).text as string}</>
              )}
              . This is an observation for inspection, not a diagnosis.
            </p>
          </section>

          <section aria-labelledby={`${noteId}-clip`} className="flex flex-col gap-3">
            <h3 id={`${noteId}-clip`} className="text-md font-bold">
              Clip
            </h3>
            {clipVideo ? (
              <video
                controls
                playsInline
                preload="metadata"
                src={`${clipVideo}#t=${Number(clip?.start_s ?? 0)},${Number(clip?.end_s ?? 0)}`}
                className="aspect-video w-full rounded-control bg-shell"
              />
            ) : (
              <div className="flex items-start gap-3 rounded-control border-2 border-dashed border-line-strong p-4">
                <VideoOff aria-hidden="true" className="mt-0.5 size-5 flex-none text-muted" strokeWidth={2.25} />
                <div>
                  <p className="font-bold">No footage attached</p>
                  {clip && typeof clip.start_s === "number" && typeof clip.end_s === "number" && (
                    <p className="text-sm text-muted">
                      Recorded track data, <Mono>{clip.start_s}–{clip.end_s} s</Mono> of the{" "}
                      <Mono>{String(clip.scenario_id ?? "replay")}</Mono> scenario (simulated).
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>

          <section aria-labelledby={`${noteId}-notes`} className="flex flex-col gap-3">
            <h3 id={`${noteId}-notes`} className="text-md font-bold">
              Notes
            </h3>
            {notes.length === 0 ? (
              <p className="text-muted">No notes yet.</p>
            ) : (
              <ol className="flex flex-col">
                {notes.map((n, i) => (
                  <li
                    key={`${n.at}-${i}`}
                    className={cn(
                      "flex flex-col gap-1 border-b border-line py-3",
                      n.kind === "assessment" && "rounded-control border-2 border-ink bg-surface px-3",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                      {n.kind === "assessment" ? (
                        <span className="inline-flex items-center gap-1.5 font-bold">
                          <Stethoscope aria-hidden="true" className="size-4" strokeWidth={2.25} />
                          Assessment note
                        </span>
                      ) : (
                        <span className="font-bold">Review note</span>
                      )}
                      <span className="text-muted">
                        {n.authorName}
                        {n.role ? ` · ${n.role}` : ""}
                      </span>
                      <Timestamp value={n.at} className="text-muted" />
                    </div>
                    <p>{n.text}</p>
                  </li>
                ))}
              </ol>
            )}
            {alert.status !== "resolved" && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor={noteId} className="text-sm font-bold">
                  {isVet ? "Assessment note" : "Note"}
                </label>
                <textarea
                  id={noteId}
                  ref={noteRef}
                  rows={3}
                  value={note}
                  aria-invalid={noteError ? true : undefined}
                  aria-describedby={`${noteId}-hint`}
                  onChange={(e) => {
                    setNote(e.target.value);
                    if (noteError) setNoteError(null);
                  }}
                  placeholder={isVet ? "What you examined and found." : "What you checked, and what happens next."}
                  className="rounded-control border-2 border-line-strong bg-bg px-3 py-2"
                />
                <p id={`${noteId}-hint`} className={cn("text-sm", noteError ? "font-bold text-danger" : "text-muted")}>
                  {noteError ?? (canResolve ? "Resolving needs a note." : "Added to the alert and the audit trail.")}
                </p>
              </div>
            )}
          </section>

          {alert.animal_id && (
            <section className="border-t border-line pt-5">
              <ButtonLink
                to={`/claims?new=1&animal=${encodeURIComponent(alert.animal_id)}&alert=${encodeURIComponent(alert.id)}`}
                icon={FilePlus2}
              >
                Record incident
              </ButtonLink>
            </section>
          )}
        </div>
      ) : null}
    </Drawer>
  );
}
