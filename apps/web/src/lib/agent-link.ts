/**
 * The fixed URL contract for opening the in-app VEYRA agent on one animal (the agent screen lives in
 * `features/agent/`): `/agent?animal=<id>&intent=find_insurance|file_claim|track_claim`.
 */
export type AgentIntent = "find_insurance" | "file_claim" | "track_claim";

export function agentHref(animalId: string, intent: AgentIntent): string {
  return `/agent?${new URLSearchParams({ animal: animalId, intent }).toString()}`;
}
