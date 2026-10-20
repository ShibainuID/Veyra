import { useMutation, useQueryClient } from "@tanstack/react-query";
import { request } from "../../lib/api";
import type { components } from "../../lib/api-types";

type Schemas = components["schemas"];
export type Conversation = Schemas["ConversationOut"];
export type AgentMessage = Schemas["AgentMessageOut"];
export type AgentCard = Schemas["AgentCard"];
export type AgentChoice = Schemas["AgentChoice"];
export type Intent = Conversation["intent"];

export const INTENTS: readonly Intent[] = ["find_insurance", "file_claim", "track_claim"];

export function isIntent(value: string | null): value is Intent {
  return value !== null && (INTENTS as readonly string[]).includes(value);
}

export function agentHref(animalId: string, intent: Intent): string {
  return `/agent?animal=${encodeURIComponent(animalId)}&intent=${intent}`;
}

export const agentKeys = {
  conversation: (id: string) => ["agent-conversation", id] as const,
};

export function startConversation(animalId: string, intent: Intent): Promise<Conversation> {
  return request<Conversation>("/agent/conversations", {
    method: "POST",
    body: JSON.stringify({ animal_id: animalId, intent }),
  });
}

export type Turn = { text: string } | { choice: { key: string; value: string | null } };

export function useSendTurn(conversationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (turn: Turn) =>
      request<Conversation>(`/agent/conversations/${encodeURIComponent(conversationId ?? "")}/messages`, {
        method: "POST",
        body: JSON.stringify(turn),
      }),
    onSuccess: async (conversation) => {
      queryClient.setQueryData(agentKeys.conversation(conversation.id), conversation);
      await queryClient.invalidateQueries({ queryKey: ["animals"] });
      await queryClient.invalidateQueries({ queryKey: ["passport"] });
    },
  });
}

/** What the agent is doing while a turn is in flight, in the farmer's words. */
export function workingLabel(key: string | undefined, animalName: string): string {
  switch (key) {
    case "prepare_application":
      return `Filling the application from ${animalName}'s passport…`;
    case "prepare_payment":
      return "Preparing the premium payment…";
    case "activation_check":
      return "Asking the insurer about cover…";
    case "incident_loss":
      return `Recording the incident and drafting the claim for ${animalName}…`;
    case "confirm_declaration":
    case "sample_rescan":
      return "Updating the claim checklist…";
    case "ownership_document":
    case "vet_check":
      return `Checking eligibility for ${animalName}…`;
    default:
      return "Reading the records…";
  }
}
