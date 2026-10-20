/**
 * Reads and writes for the money side of the app that the shared action module (features/actions)
 * doesn't cover: proposing actions, policies, recommendations, incidents, and claims. Every write
 * refreshes what it can touch, including the shell's wallet balance and approvals count.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { queryKeys } from "../../lib/query-keys";
import { invalidateAfterAction } from "../actions";

type Schemas = components["schemas"];
export type { AgentAction, ActionType, ActionStatus, Wallet } from "../actions";
export type ProposeBody = Schemas["ProposeRequest"];
export type WalletEntry = Schemas["WalletEntryOut"];
export type Policy = Schemas["PolicyDetail"];
export type Passport = Schemas["Passport"];
export type Recommendations = Schemas["RecommendationsOut"];
export type Recommendation = Schemas["Recommendation"];
export type RuleReason = Schemas["RuleReason"];
export type Explanation = Schemas["Explanation"];
export type Incident = Schemas["IncidentDetail"];
export type IncidentBody = Schemas["IncidentRequest"];
export type Claim = Schemas["ClaimDetail"];
export type ChecklistItem = Schemas["ChecklistItem"];
export type Alert = Schemas["AlertView"];
export type AnimalRow = Schemas["AnimalList"]["items"][number];

export const financeKeys = {
  policies: (animalId?: string) => ["policies", animalId ?? "all"] as const,
  recommendations: (animalId: string) => ["insurance-recommendations", animalId] as const,
  claims: ["claims"] as const,
  claim: (claimId: string) => ["claims", "detail", claimId] as const,
  incidents: ["incidents"] as const,
  incident: (incidentId: string) => ["incidents", incidentId] as const,
  alerts: (animalId?: string) => ["alerts", "finance", animalId ?? "all"] as const,
};

/** After any money-side write: the shared action refresh, plus policies, incidents, and claims. */
export async function refreshFinance(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    invalidateAfterAction(queryClient),
    queryClient.invalidateQueries({ queryKey: ["policies"] }),
    queryClient.invalidateQueries({ queryKey: financeKeys.claims }),
    queryClient.invalidateQueries({ queryKey: financeKeys.incidents }),
  ]);
}

/** The agent prepares an action; it then waits for the manager's stamp. */
export function useProposeAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProposeBody) => (await api.POST("/api/v1/agent/actions", { body })).data!,
    onSettled: () => refreshFinance(queryClient),
  });
}

/** The same action prepared again from its own references and the current records (a new version). */
export function useReviseAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: string) =>
      (await api.POST("/api/v1/agent/actions/{action_id}/revise", { params: { path: { action_id: actionId } } })).data!,
    onSettled: () => refreshFinance(queryClient),
  });
}

export function usePassport(animalId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.passport(animalId ?? ""),
    enabled: Boolean(animalId),
    queryFn: async () =>
      (await api.GET("/api/v1/animals/{animal_id}/passport", { params: { path: { animal_id: animalId! } } })).data!,
  });
}

export function usePolicies(animalId?: string) {
  return useQuery({
    queryKey: financeKeys.policies(animalId),
    queryFn: async () =>
      (await api.GET("/api/v1/policies", { params: { query: animalId ? { animal_id: animalId } : {} } })).data!.items,
  });
}

/** The unfiltered herd list (the same request the shell summary reads). */
export function useAnimals() {
  return useQuery({
    queryKey: queryKeys.animals,
    queryFn: async () => (await api.GET("/api/v1/animals")).data!,
    staleTime: 30_000,
  });
}

export function useAlerts(animalId?: string, enabled = true) {
  return useQuery({
    queryKey: financeKeys.alerts(animalId),
    enabled,
    queryFn: async () =>
      (await api.GET("/api/v1/alerts", { params: { query: animalId ? { animal_id: animalId } : {} } })).data!.items,
  });
}
