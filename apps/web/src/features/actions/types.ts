/** Agent action types, from the generated contract (`api-types.ts`). */
import type { components } from "../../lib/api-types";

type Schemas = components["schemas"];

export type AgentAction = Schemas["ActionOut"];
export type ActionType = AgentAction["action_type"];
export type ActionStatus = AgentAction["status"];
export type ActionReviewData = Schemas["ActionReview"];
export type ActionExecution = Schemas["ExecutionOut"];
export type EvidenceManifest = Schemas["EvidenceManifestOut"];
export type EvidenceItem = Schemas["EvidenceItem"];
export type DecisionRequest = Schemas["DecisionRequest"];
export type Wallet = Schemas["WalletOut"];

export type Decision = DecisionRequest["decision"];

/** Statuses where the action is still open: it can be decided, executed, or reconciled. */
export const OPEN_STATUSES: ReadonlySet<ActionStatus> = new Set(["pending_approval", "approved", "executing", "unknown"]);

export const ACTION_TITLES: Record<ActionType, string> = {
  POLICY_APPLICATION: "Policy application",
  PREMIUM_PAYMENT: "Premium payment",
  INSURER_NOTIFICATION: "Insurer notification",
  CLAIM_SUBMISSION: "Claim submission",
};

export function actionTitle(type: string): string {
  return ACTION_TITLES[type as ActionType] ?? type.toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
