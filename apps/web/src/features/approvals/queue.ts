/** Groups the agent's actions for the approval queue and turns each into a passbook line. */
import type { PassbookAmount, PassbookLineData, StampProps } from "../../components";
import { actionTitle, type AgentAction } from "../actions";

export type QueueGroupId = "awaiting" | "approved" | "unresolved" | "history";

export interface QueueGroup {
  id: QueueGroupId;
  title: string;
  description: string;
  items: AgentAction[];
}

const GROUP_OF: Record<AgentAction["status"], QueueGroupId> = {
  draft: "awaiting",
  pending_approval: "awaiting",
  approved: "approved",
  executing: "unresolved",
  unknown: "unresolved",
  succeeded: "history",
  failed: "history",
  declined: "history",
  cancelled: "history",
  expired: "history",
};

export function groupActions(actions: readonly AgentAction[]): QueueGroup[] {
  const by = (id: QueueGroupId) => actions.filter((a) => GROUP_OF[a.status] === id);
  return [
    {
      id: "awaiting",
      title: "Awaiting your stamp",
      description: "Prepared by the agent. Nothing runs until a manager approves and stamps it.",
      items: by("awaiting").sort((a, b) => a.expires_at.localeCompare(b.expires_at)),
    },
    {
      id: "approved",
      title: "Approved, not executed",
      description: "Stamped, but not yet sent to the provider.",
      items: by("approved").sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    },
    {
      id: "unresolved",
      title: "Executing or unknown",
      description: "The provider hasn't confirmed the outcome. Retry with the same key: it reconciles, it can't run twice.",
      items: by("unresolved").sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    },
    {
      id: "history",
      title: "History",
      description: "Posted, failed, declined, cancelled, and expired lines.",
      items: by("history").sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    },
  ];
}

/** Line numbers follow the order the agent prepared the actions, so a number never changes. */
export function lineNumbers(actions: readonly AgentAction[]): Map<string, number> {
  const ordered = [...actions].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  return new Map(ordered.map((a, i) => [a.id, i + 1]));
}

function payloadNumber(action: AgentAction, key: string): number | undefined {
  const value = (action.payload as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

function amountFor(action: AgentAction): PassbookAmount | undefined {
  const currency = action.review.currency ?? "USD";
  switch (action.action_type) {
    case "PREMIUM_PAYMENT": {
      if (action.review.amount_minor == null) return undefined;
      // Only a payment that ran (or may have run) moves the wallet; the rest print unsigned.
      const charged = ["pending_approval", "approved", "executing", "unknown", "succeeded"].includes(action.status);
      return charged
        ? { minor: -action.review.amount_minor, currency }
        : { minor: action.review.amount_minor, currency, label: "Not charged", signed: false };
    }
    case "POLICY_APPLICATION": {
      const premium = payloadNumber(action, "premium_minor");
      return premium !== undefined ? { minor: premium, currency, label: "Premium a year" } : undefined;
    }
    case "CLAIM_SUBMISSION": {
      const claimed = payloadNumber(action, "claimed_amount_minor");
      return claimed !== undefined ? { minor: claimed, currency, label: "Claimed" } : undefined;
    }
    default:
      return undefined;
  }
}

function stampFor(action: AgentAction, press: boolean): Omit<StampProps, "className"> | undefined {
  const done = action.execution?.completed_at ?? action.updated_at;
  switch (action.status) {
    case "succeeded":
      return { kind: "posted", at: done, by: "MGR", press };
    case "failed":
      return { kind: "failed", at: done, press };
    case "declined":
      return { kind: "declined", at: action.decided_at ?? action.updated_at, press };
    case "approved":
      return { kind: "approved", at: action.decided_at ?? action.updated_at, press };
    case "executing":
    case "unknown":
      return { kind: "unknown", at: action.updated_at, press };
    default:
      return undefined;
  }
}

/** Why a void line stopped, in words. */
export function voidReason(action: AgentAction): string | null {
  if (action.status === "expired") return "Expired before a decision";
  if (action.status !== "cancelled") return null;
  if (action.cancel_reason === "approval_stale") return "Records changed after approval";
  if (action.cancel_reason === "superseded") return "Replaced by a newer version";
  return "Cancelled";
}

export function toLine(action: AgentAction, number: number, press = false): Omit<PassbookLineData, "detail"> {
  const status: PassbookLineData["status"] =
    action.status === "pending_approval" || action.status === "draft"
      ? "awaiting"
      : action.status === "cancelled" || action.status === "expired"
        ? "void"
        : "posted";
  return {
    id: action.id,
    number,
    at: action.created_at,
    title: actionTitle(action.action_type),
    amount: amountFor(action),
    balanceMinor: action.action_type === "PREMIUM_PAYMENT" && status === "awaiting" ? (action.review.balance_after_minor ?? undefined) : undefined,
    status,
    stamp: stampFor(action, press),
    expiresAt: status === "awaiting" ? action.expires_at : undefined,
  };
}

/** Closed lines the agent can prepare again as a new version (POST /agent/actions/{id}/revise). */
export function canPrepareAgain(action: AgentAction): boolean {
  if (action.status === "cancelled") return action.cancel_reason !== "superseded";
  return action.status === "expired" || action.status === "failed" || action.status === "declined";
}
