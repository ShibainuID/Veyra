import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2Off, UserCheck } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../../components/Button";
import { EarTag } from "../../components/EarTag";
import { EmptyState, ErrorNotice } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { cn } from "../../lib/cn";
import { ApiError } from "../../lib/errors";
import { animalsQueryKey } from "../../app/use-shell-summary";
import { monitorKeys, reviewTrack, type AnimalListItem, type Replay, type Scenario, type Track } from "./api";
import { boxAt, type TrackEvent } from "./interpolate";
import { identityAt } from "./track-state";

function methodText(track: Track): string | null {
  const evidence = (track.association_evidence ?? {}) as Record<string, unknown>;
  if (track.association_method === "muzzle_match") {
    const inliers = typeof evidence.inliers === "number" ? evidence.inliers : null;
    return inliers !== null ? `Muzzle match · ${inliers} verified points` : "Muzzle match";
  }
  if (track.association_method === "manual_review" || track.association_method === "human_review") {
    return track.association_status === "unassigned" ? "Unassigned by review" : "Assigned by review";
  }
  if (track.association_method) return track.association_method.replace(/_/g, " ");
  if (evidence.event === "track_lost") return "Lost behind an obstruction";
  return null;
}

function AssignForm({
  track,
  animals,
  onDone,
}: {
  track: Track;
  animals: readonly AnimalListItem[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const selectId = useId();
  const noteId = useId();
  const confirmed = animals.filter((a) => a.identity_status === "confirmed");
  const [animalId, setAnimalId] = useState(track.animal_id ?? "");
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () => reviewTrack(track.id, animalId, note.trim() || null),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["replays"] });
      void queryClient.invalidateQueries({ queryKey: animalsQueryKey });
      void queryClient.invalidateQueries({ queryKey: monitorKeys.cameras });
      toast.show({ title: `Track ${result.track_key} assigned to ${result.animal_name ?? result.animal_id}`, tone: "ok" });
      onDone();
    },
  });
  return (
    <form
      className="mt-3 flex flex-col gap-3 rounded-control bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (animalId) mutation.mutate();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-sm font-bold">
          Animal
        </label>
        <select
          id={selectId}
          value={animalId}
          onChange={(e) => setAnimalId(e.target.value)}
          className="min-h-11 rounded-control border-2 border-line-strong bg-bg px-3"
          required
        >
          <option value="">Choose a confirmed animal…</option>
          {confirmed.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} · {a.id}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={noteId} className="text-sm font-bold">
          Review note
        </label>
        <textarea
          id={noteId}
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What you saw that confirms it, for example the ear notch."
          className="rounded-control border-2 border-line-strong bg-bg px-3 py-2"
        />
        <p className="text-sm text-muted">A person's review, recorded in the audit trail. The track keeps its camera evidence.</p>
      </div>
      {mutation.error ? (
        <ErrorNotice error={mutation.error} title={mutation.error instanceof ApiError ? mutation.error.message : undefined} />
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={!animalId} loading={mutation.isPending} loadingLabel="Assigning…">
          Assign track
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export interface TracksPanelProps {
  replay: Replay | undefined;
  scenario: Scenario | undefined;
  t: number;
  animals: readonly AnimalListItem[];
  selectedAnimalId: string | null;
  canReview: boolean;
  onSelect: (animalId: string) => void;
}

export function TracksPanel({ replay, scenario, t, animals, selectedAnimalId, canReview, onSelect }: TracksPanelProps) {
  const [assigning, setAssigning] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const unassign = useMutation({
    mutationFn: (track: Track) => reviewTrack(track.id, null, "Unassigned in review"),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["replays"] });
      void queryClient.invalidateQueries({ queryKey: animalsQueryKey });
      toast.show({ title: `Track ${result.track_key} unassigned`, tone: "neutral" });
    },
    onError: (error) =>
      toast.show({ title: "The track wasn't unassigned", body: error instanceof ApiError ? error.message : undefined, tone: "danger" }),
  });

  if (!replay) {
    return (
      <EmptyState title="No tracks yet" headingLevel={3}>
        Start a replay and each animal the camera follows is listed here, with who it is and how sure that is.
      </EmptyState>
    );
  }
  if (replay.tracks.length === 0) {
    return <p className="text-muted">The replay has started; the first tracks appear within a few seconds.</p>;
  }
  const byKey = new Map(scenario?.tracks.map((st) => [st.track_key, st]));
  return (
    <ul className="flex flex-col border-t border-line">
      {replay.tracks.map((track) => {
        const st = byKey.get(track.track_key);
        const identity = identityAt(st, track, t);
        const frame = st ? boxAt(st.frames, t, st.events as TrackEvent[]) : null;
        const visibility =
          frame && st ? st.frames.reduce((best, f) => (Math.abs(f.t - t) < Math.abs(best.t - t) ? f : best), st.frames[0]!) : null;
        const lost = (st?.events ?? []).find((e) => e.type === "track_lost");
        const isSelected = identity.status !== "unassigned" && identity.animalId === selectedAnimalId;
        const method = methodText(track);
        return (
          <li key={track.id} className={cn("border-b border-line py-3", isSelected && "bg-tag-soft")}>
            <div className="flex items-start gap-3 px-2">
              {identity.status === "associated" ? (
                <EarTag animalId={identity.animalId} state="confirmed" size="sm" />
              ) : (
                <EarTag state="none" size="sm" />
              )}
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  {identity.status === "associated" ? (
                    <button
                      type="button"
                      onClick={() => onSelect(identity.animalId)}
                      className="min-h-8 text-left font-bold underline-offset-4 hover:underline"
                      aria-pressed={isSelected}
                    >
                      {identity.name}
                    </button>
                  ) : identity.status === "uncertain" ? (
                    <StatusPill tone="uncertain" label="Identity uncertain" />
                  ) : (
                    <span className="font-bold">Unassigned track</span>
                  )}
                  <Mono className="text-sm text-muted">{track.track_key}</Mono>
                </div>
                <p className="text-sm text-muted">
                  Last observed <Timestamp value={track.last_seen} mode="absolute" className="text-ink" />
                  {visibility ? (
                    <>
                      {" "}
                      · visibility <Mono className="text-ink">{Math.round(visibility.visibility * 100)}%</Mono>
                    </>
                  ) : lost && t >= lost.t ? (
                    <> · out of view</>
                  ) : null}
                </p>
                {method && <p className="text-sm text-muted">{identity.status === "unassigned" && track.association_method === "muzzle_match" ? "Muzzle match pending" : method}</p>}
                {identity.status === "unassigned" && (
                  <p className="text-sm">Cannot be linked to a passport until someone assigns it.</p>
                )}
                {canReview && assigning !== track.id && (
                  <div className="mt-1 flex flex-wrap gap-2">
                    <Button variant="secondary" icon={UserCheck} onClick={() => setAssigning(track.id)}>
                      {identity.status === "associated" ? "Reassign" : "Assign to animal"}
                    </Button>
                    {track.animal_id && (
                      <Button
                        variant="ghost"
                        icon={Link2Off}
                        loading={unassign.isPending && unassign.variables?.id === track.id}
                        loadingLabel="Unassigning…"
                        onClick={() => unassign.mutate(track)}
                      >
                        Unassign
                      </Button>
                    )}
                  </div>
                )}
                {assigning === track.id && <AssignForm track={track} animals={animals} onDone={() => setAssigning(null)} />}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
