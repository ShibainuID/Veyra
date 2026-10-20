import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { animalsQueryKey } from "../../app/use-shell-summary";
import { api, request } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { ApiError } from "../../lib/errors";

export type Scenario = components["schemas"]["Scenario"];
export type ScenarioTrack = components["schemas"]["ScenarioTrack"];
export type Camera = components["schemas"]["CameraOut"];
export type Replay = components["schemas"]["ReplayOut"];
export type ReplayStarted = components["schemas"]["ReplayStarted"];
export type Track = components["schemas"]["TrackOut"];
export type AlertView = components["schemas"]["AlertView"];
export type AnimalListItem = components["schemas"]["AnimalListItem"];
export type AnimalList = components["schemas"]["AnimalList"];

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new ApiError(500, "HTTP_ERROR", "The server sent an empty response.");
  return data;
}

export const monitorKeys = {
  scenarios: ["demo", "replays"] as const,
  cameras: ["cameras"] as const,
  replay: (id: string) => ["replays", id] as const,
  alerts: ["alerts"] as const,
  alert: (id: string) => ["alerts", id] as const,
};

export function useScenarios() {
  return useQuery({
    queryKey: monitorKeys.scenarios,
    queryFn: async () => must((await api.GET("/api/v1/demo/replays")).data),
    staleTime: 5 * 60_000,
  });
}

export function useCameras(live: boolean) {
  return useQuery({
    queryKey: monitorKeys.cameras,
    queryFn: async () => must((await api.GET("/api/v1/cameras")).data).items,
    refetchInterval: live ? 3000 : false,
  });
}

export function useAnimals(live: boolean) {
  return useQuery({
    queryKey: animalsQueryKey,
    queryFn: () => request<AnimalList>("/animals"),
    refetchInterval: live ? 4000 : false,
  });
}

/** Polls while the replay runs; once it settles, one last read carries the final tracks and alerts. */
export function useReplay(replayId: string | null) {
  return useQuery({
    queryKey: monitorKeys.replay(replayId ?? "none"),
    queryFn: async () =>
      must((await api.GET("/api/v1/replays/{replay_id}", { params: { path: { replay_id: replayId! } } })).data),
    enabled: replayId !== null,
    staleTime: 0,
    refetchInterval: (query) => (query.state.data?.status === "running" || !query.state.data ? 1000 : false),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 3,
  });
}

export async function startReplay(scenarioId: string): Promise<ReplayStarted> {
  const { data } = await api.POST("/api/v1/demo/replays/{scenario_id}/start", {
    params: { path: { scenario_id: scenarioId } },
  });
  return must(data);
}

export function useAlerts(live: boolean) {
  return useQuery({
    queryKey: monitorKeys.alerts,
    queryFn: async () => must((await api.GET("/api/v1/alerts")).data).items,
    refetchInterval: live ? 3000 : 30_000,
  });
}

export async function reviewTrack(trackId: string, animalId: string | null, note: string | null): Promise<Track> {
  const { data } = await api.PATCH("/api/v1/tracks/{track_id}", {
    params: { path: { track_id: trackId } },
    body: { animal_id: animalId, note },
  });
  return must(data);
}

/* ---------- Monitor session state: the chosen scenario and the replay it started ---------- */

interface MonitorState {
  scenarioId: string | null;
  replayId: string | null;
  cameraId: string | null;
}

const STORAGE_KEY = "veyra.monitor";
let state: MonitorState = read();
const listeners = new Set<() => void>();

function read(): MonitorState {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<MonitorState>;
      return { scenarioId: parsed.scenarioId ?? null, replayId: parsed.replayId ?? null, cameraId: parsed.cameraId ?? null };
    }
  } catch {
    // Storage blocked: the choice lasts until the page reloads.
  }
  return { scenarioId: null, replayId: null, cameraId: null };
}

export function setMonitorState(patch: Partial<MonitorState>): void {
  state = { ...state, ...patch };
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
  listeners.forEach((l) => l());
}

export function useMonitorState(): MonitorState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}
