import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, PlayCircle } from "lucide-react";
import { useEffect, useId, useMemo, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { Button } from "../../components/Button";
import { ErrorNotice, LoadingRegion, Skeleton } from "../../components/feedback";
import { Mono, Timestamp } from "../../components/figures";
import { PageHeader, Section } from "../../components/layout";
import { Provenance } from "../../components/Provenance";
import { StatusPill } from "../../components/StatusPill";
import { useToast } from "../../components/Toast";
import { queryKeys } from "../../lib/query-keys";
import { cn } from "../../lib/cn";
import { ApiError } from "../../lib/errors";
import { formatCountdown } from "../../lib/format";
import { useRole } from "../../lib/role-store";
import { Page } from "../../pages/Page";
import { AlertDrawer } from "../alerts/AlertDrawer";
import { AlertFeed, AlertsTable } from "../alerts/AlertLists";
import { alertSubject, KIND_LABEL, type AlertView } from "../alerts/alert-copy";
import {
  monitorKeys,
  setMonitorState,
  startReplay,
  useAlerts,
  useAnimals,
  useCameras,
  useMonitorState,
  useReplay,
  useScenarios,
  type Scenario,
} from "./api";
import { CameraStage } from "./CameraStage";
import "./monitor.css";
import { boxAt, type TrackEvent } from "./interpolate";
import { PenMap, type LivePosition } from "./PenMap";
import { identityAt, identityContext } from "./track-state";
import { TracksPanel } from "./TracksPanel";
import { LOCAL_RATE, useReplayClock } from "./use-replay-clock";

const SCENARIO_LABEL: Record<string, string> = {
  healthy: "Healthy replay",
  anomaly: "Reduced-movement replay",
  lost_identity: "Lost identity replay",
  crowded_scan: "Crowded scan replay",
  veo_barn: "Pen A camera footage",
};
const SCENARIO_ORDER = ["healthy", "anomaly", "lost_identity", "crowded_scan", "veo_barn"];

function scenarioLabel(s: Scenario): string {
  return SCENARIO_LABEL[s.id] ?? s.label;
}

function ScenarioPicker({
  scenarios,
  value,
  onChange,
}: {
  scenarios: readonly Scenario[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-sm font-bold">Scenario</legend>
      <div className="flex flex-wrap gap-2">
        {scenarios.map((s) => {
          const checked = s.id === value;
          return (
            <label
              key={s.id}
              className={cn(
                "flex min-h-14 cursor-pointer flex-col justify-center rounded-control border-2 px-4 py-1.5",
                "has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink",
                checked ? "border-ink bg-ink text-white" : "border-ink bg-bg hover:bg-surface-2",
              )}
            >
              <input type="radio" name={name} value={s.id} checked={checked} onChange={() => onChange(s.id)} className="sr-only" />
              <span className="font-bold">{scenarioLabel(s)}</span>
              <span className={cn("text-sm", checked ? "text-on-shell-muted" : "text-muted")}>
                {s.footage ? "Camera footage" : "Recorded scenario"} · {s.source}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

const STATUS_COPY: Record<string, { tone: "ok" | "neutral" | "danger" | "awaiting"; label: string }> = {
  running: { tone: "awaiting", label: "Replaying" },
  finished: { tone: "ok", label: "Replay finished" },
  stopped: { tone: "neutral", label: "Replay stopped" },
  failed: { tone: "danger", label: "Replay failed" },
};

export function MonitorScreen() {
  const { alertId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const role = useRole();
  const queryClient = useQueryClient();
  const state = useMonitorState();
  const selectedAnimalId = params.get("animal");
  const cameraParam = params.get("camera");

  const scenariosQuery = useScenarios();
  const replayQuery = useReplay(state.replayId);
  const replay = replayQuery.data;
  const live = replay?.status === "running";
  const camerasQuery = useCameras(live);
  const animalsQuery = useAnimals(live);
  const alertsQuery = useAlerts(live);

  const scenarios = useMemo(
    () =>
      [...(scenariosQuery.data?.scenarios ?? [])].sort(
        (a, b) => (SCENARIO_ORDER.indexOf(a.id) + 99) % 99 - ((SCENARIO_ORDER.indexOf(b.id) + 99) % 99),
      ),
    [scenariosQuery.data],
  );
  const cameras = camerasQuery.data ?? scenariosQuery.data?.cameras ?? [];
  const cameraFilter = cameraParam ?? state.cameraId;
  const visibleScenarios = cameraFilter ? scenarios.filter((s) => s.camera_id === cameraFilter) : scenarios;
  const scenario =
    visibleScenarios.find((s) => s.id === state.scenarioId) ??
    (replay ? visibleScenarios.find((s) => s.id === replay.scenario_id) : undefined) ??
    visibleScenarios[0];
  const scenarioReplay = replay && scenario && replay.scenario_id === scenario.id ? replay : undefined;
  // A scenario with footage plays back in real time, so the clip and the overlay share one clock.
  const clock = useReplayClock(scenarioReplay, scenario?.duration_s ?? 0, scenario?.clip ? 1 : LOCAL_RATE);
  const camera = cameras.find((c) => c.id === scenario?.camera_id);

  // A replay that no longer exists (a demo reset) is forgotten.
  useEffect(() => {
    if (replayQuery.error instanceof ApiError && replayQuery.error.status === 404) setMonitorState({ replayId: null });
  }, [replayQuery.error]);

  // Alerts raised by this replay land in the farm-wide list, the herd, and the passports too; so
  // do the last sightings once the replay settles.
  const replayAlertCount = replay?.alerts.length ?? 0;
  const replayStatus = replay?.status;
  useEffect(() => {
    if (replayAlertCount === 0 && (replayStatus === undefined || replayStatus === "running")) return;
    for (const queryKey of [monitorKeys.alerts, queryKeys.animals, queryKeys.passports, ["observations"], queryKeys.auditEvents])
      void queryClient.invalidateQueries({ queryKey });
  }, [replayAlertCount, replayStatus, queryClient]);

  // A new alert from the running replay is announced, since the feed may sit below the fold.
  const toast = useToast();
  const announced = useRef<Set<string> | null>(null);
  useEffect(() => {
    const alerts = replay?.alerts ?? [];
    if (announced.current === null || !live) {
      announced.current = new Set(alerts.map((a) => a.id));
      return;
    }
    for (const alert of alerts) {
      if (announced.current.has(alert.id)) continue;
      announced.current.add(alert.id);
      toast.show({
        tone: "neutral",
        title: `New alert · ${alertSubject(alert)} · ${KIND_LABEL[alert.kind]}`,
        body: "It is in the alert feed. An alert asks for an inspection; it is not a diagnosis.",
        duration: 8000,
      });
    }
  }, [replay?.alerts, live, toast]);

  const start = useMutation({
    mutationFn: (scenarioId: string) => startReplay(scenarioId),
    onSuccess: (started) => {
      setMonitorState({ replayId: started.replay_id, scenarioId: started.scenario_id });
      void queryClient.invalidateQueries({ queryKey: monitorKeys.replay(started.replay_id) });
    },
  });

  const animals = useMemo(() => animalsQuery.data?.items ?? [], [animalsQuery.data]);
  const context = useMemo(() => identityContext(scenarioReplay, animals), [scenarioReplay, animals]);

  // Footage plays on its own once the server replay settles, so the clip and its overlay run together.
  const autoPlayed = useRef<string | null>(null);
  const { play } = clock;
  useEffect(() => {
    if (!scenario?.clip || !scenarioReplay || scenarioReplay.status !== "finished") return;
    if (autoPlayed.current === scenarioReplay.id) return;
    autoPlayed.current = scenarioReplay.id;
    play();
  }, [scenario?.clip, scenarioReplay, play]);

  const livePositions: LivePosition[] = useMemo(() => {
    if (!scenarioReplay || !scenario) return [];
    const server = new Map(scenarioReplay.tracks.map((t) => [t.track_key, t]));
    return scenario.tracks.flatMap((st) => {
      const box = boxAt(st.frames, clock.t, st.events as TrackEvent[]);
      if (!box) return [];
      const identity = identityAt(st, server.get(st.track_key), clock.t, context);
      return [
        {
          key: st.track_key,
          cameraId: scenario.camera_id,
          box,
          animalId: identity.status === "associated" ? identity.animalId : null,
          trackKey: st.track_key,
        },
      ];
    });
  }, [scenarioReplay, scenario, clock.t, context]);

  const feed = useMemo(() => {
    const byId = new Map<string, AlertView>();
    for (const a of alertsQuery.data ?? []) if (a.status === "open") byId.set(a.id, a);
    for (const a of replay?.alerts ?? []) byId.set(a.id, a);
    return [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [alertsQuery.data, replay]);

  const selectAnimal = (animalId: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (next.get("animal") === animalId) next.delete("animal");
        else next.set("animal", animalId);
        return next;
      },
      { replace: true },
    );

  const canStart = role.role === "manager" || role.role === "operator";
  const status = scenarioReplay ? STATUS_COPY[scenarioReplay.status] : null;
  const duration = scenario?.duration_s ?? 0;
  const selectedName = animals.find((a) => a.id === selectedAnimalId)?.name;

  return (
    <Page>
      <PageHeader
        title="Monitor"
        meta={
          selectedName ? (
            <>
              Following <strong className="text-ink">{selectedName}</strong> <Mono>({selectedAnimalId})</Mono>
            </>
          ) : (
            "Recorded camera replays, the tracks they follow, and the alerts they raise."
          )
        }
      />

      {scenariosQuery.isPending ? (
        <LoadingRegion label="Loading the recorded scenarios">
          <Skeleton height="56px" />
        </LoadingRegion>
      ) : scenariosQuery.error ? (
        <ErrorNotice error={scenariosQuery.error} title="The recorded scenarios couldn't load" onRetry={() => void scenariosQuery.refetch()} />
      ) : (
        <div className="flex flex-col gap-4 border-b-2 border-ink pb-6 xl:flex-row xl:items-end xl:justify-between">
          <ScenarioPicker
            scenarios={visibleScenarios}
            value={scenario?.id ?? null}
            onChange={(id) => setMonitorState({ scenarioId: id })}
          />
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-bold">Camera</span>
              <select
                value={cameraFilter ?? ""}
                onChange={(e) => {
                  const id = e.target.value || null;
                  setMonitorState({ cameraId: id });
                  setParams(
                    (prev) => {
                      const next = new URLSearchParams(prev);
                      next.delete("camera");
                      return next;
                    },
                    { replace: true },
                  );
                }}
                className="min-h-12 rounded-control border-2 border-ink bg-bg px-3 font-bold"
              >
                <option value="">All cameras</option>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="primary"
              icon={PlayCircle}
              disabled={!scenario || !canStart}
              loading={start.isPending}
              loadingLabel="Starting…"
              onClick={() => scenario && start.mutate(scenario.id)}
            >
              {scenarioReplay ? "Start again" : "Start replay"}
            </Button>
          </div>
        </div>
      )}
      {!canStart && <p className="mt-3 text-sm text-muted">Only a manager or operator can start a replay. You can still watch and review alerts.</p>}
      {start.error ? <ErrorNotice className="mt-4" error={start.error} title="The replay didn't start" /> : null}

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-4">
          {scenario && (
            <p className="flex flex-wrap items-center gap-2 text-muted">
              <Provenance source={scenario.source === "prototype" ? "prototype" : "simulated"} />
              <span className="min-w-0">{scenario.description}</span>
            </p>
          )}
          <CameraStage
            scenario={scenario}
            replay={scenarioReplay}
            clock={clock}
            selectedAnimalId={selectedAnimalId}
            cameraName={camera?.name ?? scenario?.camera_name ?? null}
            animals={animals}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              icon={clock.playing ? Pause : Play}
              disabled={!scenarioReplay || live}
              onClick={clock.playing ? clock.pause : clock.play}
            >
              {clock.playing ? "Pause" : "Play back"}
            </Button>
            <label className="flex min-w-[12rem] flex-1 items-center gap-3">
              <span className="sr-only">Replay position</span>
              <input
                type="range"
                min={0}
                max={duration}
                step={scenario?.clip ? 0.1 : 0.5}
                value={Math.min(duration, clock.t)}
                disabled={!scenarioReplay || live}
                onChange={(e) => clock.seek(Number(e.target.value))}
                className="replay-scrubber h-11 min-w-0 flex-1"
                aria-valuetext={`${formatCountdown(clock.t * 1000)} of ${formatCountdown(duration * 1000)}`}
              />
            </label>
            <Mono className="font-bold">
              {formatCountdown(clock.t * 1000)} <span className="text-muted">/ {formatCountdown(duration * 1000)}</span>
            </Mono>
            {status && <StatusPill tone={status.tone} label={status.label} />}
          </div>
          {scenarioReplay?.anchor_at && (
            <p className="text-sm text-muted">
              Observed at{" "}
              <Timestamp
                value={new Date(new Date(scenarioReplay.anchor_at).getTime() + clock.t * 1000).toISOString()}
                mode="absolute"
                className="text-ink"
              />{" "}
              in the recording.
            </p>
          )}
          {live && <p className="text-sm text-muted">The overlay follows the replay as the server ingests it. Scrub once it finishes.</p>}

          <Section title="Pen map" description="Cameras where they hang, and each tag by the camera that last saw it.">
            {camerasQuery.isPending && !cameras.length ? (
              <Skeleton height="220px" />
            ) : (
              <PenMap
                cameras={cameras}
                animals={animals}
                live={livePositions}
                selectedAnimalId={selectedAnimalId}
                activeCameraId={scenario?.camera_id ?? null}
                onSelect={selectAnimal}
              />
            )}
          </Section>
        </div>

        <div className="flex min-w-0 flex-col">
          <Section title="Alert feed">
            <AlertFeed alerts={feed} loading={alertsQuery.isPending} />
          </Section>
          <Section title="Tracks">
            <TracksPanel
              replay={scenarioReplay}
              scenario={scenario}
              t={clock.t}
              animals={animals}
              selectedAnimalId={selectedAnimalId}
              canReview={canStart}
              onSelect={selectAnimal}
            />
          </Section>
        </div>
      </div>

      <Section title="Alerts" description="Every alert on the farm. Open one to acknowledge it, add a note, or resolve it.">
        <AlertsTable
          alerts={alertsQuery.data ?? []}
          loading={alertsQuery.isPending}
          error={alertsQuery.error}
          onRetry={() => void alertsQuery.refetch()}
        />
      </Section>

      <AlertDrawer
        alertId={alertId ?? null}
        onClose={() => navigate({ pathname: "/monitor", search: params.toString() ? `?${params.toString()}` : "" })}
      />
    </Page>
  );
}
