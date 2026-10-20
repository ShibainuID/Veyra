import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { queryKeys, type ActionListParams } from "../../lib/query-keys";
import { idempotencyKeyFor } from "./idempotency";
import type { AgentAction, Decision, Wallet } from "./types";

/** The error middleware throws on every non-2xx response, so a returned result always has data. */
function must<T>(result: { data?: T }): T {
  if (result.data === undefined) throw new Error("The response had no body.");
  return result.data;
}

export async function fetchAction(actionId: string): Promise<AgentAction> {
  return must(await api.GET("/api/v1/agent/actions/{action_id}", { params: { path: { action_id: actionId } } }));
}

export function useAction(actionId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.action(actionId ?? ""),
    queryFn: () => fetchAction(actionId!),
    enabled: Boolean(actionId),
    staleTime: 5_000,
  });
}

export function useActions(params: ActionListParams = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.actionList(params),
    queryFn: async () => must(await api.GET("/api/v1/agent/actions", { params: { query: params } })).items,
    enabled,
  });
}

export function useWallet() {
  return useQuery({
    queryKey: queryKeys.wallet,
    queryFn: async (): Promise<Wallet> => must(await api.GET("/api/v1/wallet")),
    staleTime: 15_000,
  });
}

/** Everything an approval, decline, or execution can change: herd, passports, actions, wallet, audit. */
export async function invalidateAfterAction(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.animals }),
    queryClient.invalidateQueries({ queryKey: queryKeys.passports }),
    queryClient.invalidateQueries({ queryKey: queryKeys.actions }),
    queryClient.invalidateQueries({ queryKey: queryKeys.wallet }),
    queryClient.invalidateQueries({ queryKey: queryKeys.auditEvents }),
  ]);
}

export interface DecisionInput {
  /** The action as the manager reviewed it: its payload hash and version go with the decision. */
  action: Pick<AgentAction, "id" | "payload_hash" | "version">;
  decision: Decision;
  note?: string;
}

export function useActionDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ action, decision, note }: DecisionInput) =>
      must(
        await api.POST("/api/v1/agent/actions/{action_id}/decision", {
          params: { path: { action_id: action.id } },
          body: { decision, payload_hash: action.payload_hash, version: action.version, note: note?.trim() || null },
        }),
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.action(updated.id), updated);
    },
  });
}

/**
 * Runs an approved action. The Idempotency-Key is created once per action and reused on every
 * retry, so a second press after a timeout reconciles with the provider instead of paying twice.
 */
export function useExecuteAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: string) =>
      must(
        await api.POST("/api/v1/agent/actions/{action_id}/execute", {
          params: { path: { action_id: actionId }, header: { "Idempotency-Key": idempotencyKeyFor(actionId) } },
        }),
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.action(updated.id), updated);
    },
  });
}
